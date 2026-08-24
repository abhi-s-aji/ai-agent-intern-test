import sys
import time

from app.agent import Session, SupportAgent


def type_text(text, delay=0.025):
    for character in text:
        sys.stdout.write(character)
        sys.stdout.flush()
        time.sleep(delay)


def show_result(agent, session, user_message):
    print()
    print("-" * 72)

    type_text("You: ", 0.04)
    type_text(user_message, 0.025)

    print()
    time.sleep(0.7)

    response = agent.respond(user_message, session)

    type_text("\nAgent: ", 0.04)
    type_text(response["answer"], 0.012)
    print()

    if response.get("sources"):
        print("\nSources:")
        for source in response["sources"]:
            print(f"  - {source}")

    if response.get("tool"):
        print(f"\nTool used: {response['tool']}")

    if response.get("handoff"):
        print("\nHuman handoff: recommended")

    time.sleep(1)


def main():
    agent = SupportAgent()
    session = Session()

    print()
    print("=" * 72)
    print("ASTER & ROW SUPPORT AGENT")
    print("=" * 72)
    print()

    type_text("Starting support agent", 0.04)
    for _ in range(3):
        type_text(".", 0.25)
    print("\n")

    time.sleep(1)

    print("DEMO 1 — KNOWLEDGE BASE / RAG")
    show_result(
        agent,
        session,
        "What is the standard return window?",
    )

    print("\n")
    print("DEMO 2 — ORDER LOOKUP")
    show_result(
        agent,
        session,
        "Where is ORD-1007?",
    )

    print("\n")
    print("DEMO 3 — MULTI-TURN CONVERSATION")
    show_result(
        agent,
        session,
        "When will it arrive?",
    )

    print("\n")
    print("DEMO 4 — SAFE ABSTENTION")
    show_result(
        agent,
        session,
        "Are all the bag materials certified vegan?",
    )

    print()
    print("=" * 72)
    print("DEMO COMPLETE")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
