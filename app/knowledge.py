"""
Knowledge base loader module for loading and chunking Markdown files with YAML front matter.
"""

import os
from typing import Any, Dict, List, Tuple
import frontmatter


def split_markdown_by_headings(content: str) -> List[Tuple[str, List[str], str]]:
    """
    Splits markdown content into sections based on headings (#, ##, etc.).
    
    Retains the heading path (the list of parent headings leading to the section).
    Sections with empty content are omitted.
    
    Args:
        content: The raw markdown content string.
        
    Returns:
        A list of tuples: (heading, heading_path, content_text)
    """
    lines = content.splitlines()
    chunks: List[Tuple[str, List[str], str]] = []
    
    current_heading_path: List[str] = []
    current_content_lines: List[str] = []
    current_heading = ""
    
    for line in lines:
        # Check if the line is an ATX heading (starts with '#' characters)
        if line.startswith('#'):
            # Count the number of hashes to determine the level
            num_hashes = 0
            for char in line:
                if char == '#':
                    num_hashes += 1
                else:
                    break
            
            # Check if the hashes are followed by whitespace or if the line has nothing else
            is_heading = False
            if num_hashes > 0:
                if num_hashes == len(line):
                    is_heading = True
                elif line[num_hashes].isspace():
                    is_heading = True
            
            if is_heading:
                # Extract heading text and clean it
                heading_text = line[num_hashes:].strip()
                heading_text = heading_text.rstrip('#').strip()
                
                # Save previous section if it has content
                content_str = "\n".join(current_content_lines).strip()
                if content_str:
                    chunks.append((current_heading, list(current_heading_path), content_str))
                
                # Update the heading path according to the heading level
                if len(current_heading_path) >= num_hashes:
                    current_heading_path = current_heading_path[:num_hashes - 1]
                current_heading_path.append(heading_text)
                
                current_heading = heading_text
                current_content_lines = []
                continue
                
        current_content_lines.append(line)
        
    # Append the final section if it has content
    content_str = "\n".join(current_content_lines).strip()
    if content_str:
        chunks.append((current_heading, list(current_heading_path), content_str))
        
    return chunks


def load_documents(path: str) -> List[Dict[str, Any]]:
    """
    Reads all Markdown files in the specified directory, parses their front matter
    metadata using python-frontmatter, splits the content by headings, and returns
    a list of structured chunk objects.
    
    Args:
        path: Path to the directory containing Markdown files.
        
    Returns:
        A list of dictionaries, where each dictionary represents a chunk with keys:
        - filename: Name of the markdown file.
        - document_id: Unique identifier for the document.
        - title: Title of the document.
        - status: Document status.
        - effective_date: Date when the document became/becomes effective.
        - audience: Target audience.
        - policy_authority: Policy authority level.
        - heading: Heading of the specific section.
        - heading_path: Path of headings leading to this section.
        - content: Cleaned text content of the section.
        And any other metadata fields present in the front matter.
    """
    if not os.path.isdir(path):
        raise ValueError(f"The path '{path}' is not a valid directory.")
        
    chunks: List[Dict[str, Any]] = []
    
    # Process files in sorted order for determinism
    filenames = sorted([
        f for f in os.listdir(path)
        if f.endswith(('.md', '.markdown')) and os.path.isfile(os.path.join(path, f))
    ])
    
    required_keys = [
        "document_id",
        "title",
        "status",
        "effective_date",
        "audience",
        "policy_authority",
    ]
    
    for filename in filenames:
        filepath = os.path.join(path, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)
            
        metadata = post.metadata
        content = post.content
        
        # Split document into chunks by heading
        split_sections = split_markdown_by_headings(content)
        
        for heading, heading_path, section_content in split_sections:
            chunk = {
                "filename": filename,
                "heading": heading,
                "heading_path": heading_path,
                "content": section_content,
                **metadata
            }
            
            # Ensure all required keys exist (set to None if missing)
            for key in required_keys:
                if key not in chunk:
                    chunk[key] = None
                    
            chunks.append(chunk)
            
    return chunks
