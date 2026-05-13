import argparse
import sys

from dotenv import load_dotenv

from research_agent import build_graph


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="LangGraph multi-agent research workflow (Researcher -> Writer -> Reviewer).",
    )
    parser.add_argument("topic", help="The research topic to investigate and write about.")
    parser.add_argument(
        "--show-notes",
        action="store_true",
        help="Print the researcher's notes and reviewer feedback in addition to the article.",
    )
    args = parser.parse_args()

    app = build_graph()
    result = app.invoke({"topic": args.topic, "revision_count": 0})

    if args.show_notes:
        print("=" * 60)
        print("RESEARCH NOTES")
        print("=" * 60)
        print(result.get("research_notes", ""))
        print()
        print("=" * 60)
        print("REVIEWER FEEDBACK (last iteration)")
        print("=" * 60)
        print(result.get("feedback", ""))
        print()
        print("=" * 60)
        print(f"FINAL ARTICLE (revisions: {result.get('revision_count', 0)})")
        print("=" * 60)

    print(result.get("final_output") or result.get("draft", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
