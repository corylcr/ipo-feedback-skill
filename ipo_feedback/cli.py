"""CLI entry point for ipo-feedback."""
import argparse
import json
import sys
from datetime import datetime

from .exchanges.bse import BSE
from .exchanges.sse import SSE
from .exchanges.szse import SZSE
from .models import FeedbackReport, ProjectFeedback, FeedbackDocument
from . import config


def fetch_report(exchange: str, days: int, download: bool, parse: bool) -> FeedbackReport:
    """Fetch feedback report from the specified exchange."""
    if exchange == "bse":
        scraper = BSE()
    elif exchange == "sse":
        scraper = SSE()
    elif exchange == "szse":
        scraper = SZSE()
    else:
        print(f"⚠ Unknown exchange: {exchange}")
        sys.exit(1)

    report = scraper.fetch_projects(days=days)

    if download:
        report = scraper.download_and_parse(report, parse_text=parse)

    return report


def print_markdown(report: FeedbackReport, cleaned_files: list[str] | None = None):
    """Print report as Markdown to stdout."""
    from .analyzer import analyze_inquiry_letter, analyze_feedback_reply
    from .prospectus import extract_prospectus_summary
    from pathlib import Path

    exchange_name = config.EXCHANGE_NAMES.get(report.exchange, report.exchange)
    print(f"\n# {exchange_name} IPO Feedback Report")
    print(f"**Period**: {report.date_range}\n")

    if not report.projects:
        print("No new feedback or registration drafts in this period.\n")
        return

    # Summary
    inquiry_count = sum(1 for p in report.projects if p.inquiry)
    reply_count = sum(1 for p in report.projects if p.reply)
    prospectus_count = sum(1 for p in report.projects if p.prospectus)
    parts = []
    if inquiry_count:
        parts.append(f"inquiry letters **{inquiry_count}**")
    if reply_count:
        parts.append(f"feedback replies **{reply_count}**")
    if prospectus_count:
        parts.append(f"registration drafts **{prospectus_count}**")
    print(f"Total **{len(report.projects)}** projects updated: {', '.join(parts)}\n")
    print("---\n")

    # Projects
    for project in report.projects:
        code_str = f" ({project.stock_code})" if project.stock_code else ""
        print(f"## {project.company_name}{code_str}\n")

        # --- Inquiry Letter ---
        if project.inquiry:
            doc = project.inquiry
            print(f"### Inquiry Letter\n")
            print(f"- Published: {doc.publish_date}")
            print(f"- PDF: [{doc.title}]({doc.pdf_url})\n")

            analysis = analyze_inquiry_letter(doc.content_text)
            if analysis["questions"]:
                print(f"**{len(analysis['questions'])} questions raised:**\n")
                for q in analysis["questions"]:
                    print(f"{q['number']}. **{q['title']}**")
                    if q["focus"]:
                        print(f"   Focus: {q['focus'][:200]}")
                    print()

        # --- Feedback Reply ---
        if project.reply:
            doc = project.reply
            print(f"### Feedback Reply\n")
            print(f"- Published: {doc.publish_date}")
            print(f"- PDF: [{doc.title}]({doc.pdf_url})\n")

            analysis = analyze_feedback_reply(doc.content_text)
            if analysis["topics"]:
                print(f"**{len(analysis['topics'])} topics addressed:**\n")
                for t in analysis["topics"]:
                    print(f"{t['number']}. **{t['title']}**")
                    if t["approach"]:
                        print(f"   Reply: {t['approach'][:200]}")
                    print()

        # --- Prospectus Registration Draft ---
        if project.prospectus:
            doc = project.prospectus
            print(f"### Registration Draft\n")
            print(f"- Published: {doc.publish_date}")
            print(f"- PDF: [{doc.title}]({doc.pdf_url})\n")

            pdf_path = Path(doc.pdf_path)
            if pdf_path.exists():
                summary = extract_prospectus_summary(pdf_path)
                if summary.get("main_business"):
                    print(f"**Main Business:**\n")
                    print(f"{summary['main_business'][:500]}\n")
                if summary.get("financials"):
                    print(f"**Key Financials:**\n")
                    f = summary["financials"]
                    if "revenue" in f:
                        print(f"- Revenue: {f['revenue']}")
                    if "net_profit" in f:
                        print(f"- Net Profit: {f['net_profit']}")
                    if "gross_margin" in f:
                        print(f"- Gross Margin: {f['gross_margin']}")
                    if "roe" in f:
                        print(f"- ROE: {f['roe']}")
                    print()
            else:
                print(f"*(PDF not downloaded yet)*\n")

        print("---\n")

    # Cleanup summary
    if cleaned_files:
        print(f"**Trash**: {len(cleaned_files)} old files (>30 days) moved to trash")
        for name in cleaned_files:
            print(f"- {name}")


def print_json(report: FeedbackReport):
    """Print report as JSON to stdout."""
    def doc_to_dict(doc: FeedbackDocument | None) -> dict | None:
        if doc is None:
            return None
        return {
            "title": doc.title,
            "publish_date": doc.publish_date,
            "pdf_url": doc.pdf_url,
            "pdf_path": doc.pdf_path,
            "content_text": doc.content_text,
        }

    output = {
        "exchange": report.exchange,
        "date_range": report.date_range,
        "projects": [
            {
                "company_name": p.company_name,
                "stock_code": p.stock_code,
                "inquiry": doc_to_dict(p.inquiry),
                "reply": doc_to_dict(p.reply),
                "prospectus": doc_to_dict(p.prospectus),
            }
            for p in report.projects
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def setup_schedule():
    """Set up a daily cron job to run at 9:30 AM."""
    import platform
    import subprocess

    print("📋 Daily Schedule Setup")
    print("This will set up a cron job to fetch IPO feedback daily at 9:30 AM.")
    print("The job will fetch the previous day's data from all exchanges.\n")

    answer = input("Do you want to set up this schedule? (y/N): ").strip().lower()
    if answer != 'y':
        print("Schedule setup cancelled.")
        return

    # Get the path to the ipo-feedback command
    try:
        result = subprocess.run(["which", "ipo-feedback"], capture_output=True, text=True)
        cmd_path = result.stdout.strip()
    except Exception:
        cmd_path = "ipo-feedback"

    if not cmd_path:
        print("✗ Could not find ipo-feedback command. Make sure it's installed.")
        sys.exit(1)

    # Get the project directory (where downloads/ lives)
    project_dir = config.PROJECT_ROOT

    # Cron job: run at 9:30 AM daily, fetch yesterday's data from all exchanges
    cron_line = f"30 9 * * * cd {project_dir} && {cmd_path} fetch --exchange all --days 1 >> {project_dir}/schedule.log 2>&1"

    if platform.system() == "Darwin" or platform.system() == "Linux":
        # Get existing crontab
        try:
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            existing_cron = result.stdout if result.returncode == 0 else ""
        except Exception:
            existing_cron = ""

        # Check if already scheduled
        if "ipo-feedback" in existing_cron:
            print("⚠ Schedule already exists. Current cron job:")
            for line in existing_cron.splitlines():
                if "ipo-feedback" in line:
                    print(f"  {line}")
            print("\nTo update, run: crontab -e")
            return

        # Add new cron job
        new_cron = existing_cron.rstrip() + "\n" + cron_line + "\n"
        process = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
        process.communicate(input=new_cron)

        if process.returncode == 0:
            print(f"\n✅ Schedule set up successfully!")
            print(f"   Runs daily at 9:30 AM")
            print(f"   Fetches previous day's IPO feedback from all exchanges")
            print(f"   Log file: {project_dir}/schedule.log")
            print(f"\nTo view: crontab -l")
            print(f"To remove: crontab -e (delete the ipo-feedback line)")
        else:
            print("✗ Failed to set up schedule")
    else:
        print(f"✗ Unsupported platform: {platform.system()}")
        print(f"  Please add this cron job manually:")
        print(f"  {cron_line}")


def main():
    parser = argparse.ArgumentParser(
        prog="ipo-feedback",
        description="IPO Feedback Skill — Scrape and parse IPO feedback documents from BSE/SSE/SZSE",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch IPO feedback documents")
    fetch_parser.add_argument(
        "--exchange", "-e",
        choices=["bse", "sse", "szse", "all"],
        default="bse",
        help="Exchange to scrape (default: bse)",
    )
    fetch_parser.add_argument(
        "--days", "-d",
        type=int,
        default=1,
        choices=range(1, 41),
        metavar="[1-40]",
        help="Number of days to look back, max 40 (default: 1, i.e. yesterday)",
    )
    fetch_parser.add_argument(
        "--no-download",
        action="store_true",
        help="Only list documents, don't download PDFs",
    )
    fetch_parser.add_argument(
        "--no-parse",
        action="store_true",
        help="Download PDFs but don't extract text",
    )
    fetch_parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    # schedule command
    subparsers.add_parser("schedule", help="Set up daily auto-fetch at 9:30 AM")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "fetch":
        # Auto-cleanup old files (>30 days)
        from .cleanup import cleanup_old_files
        cleaned = cleanup_old_files(config.DOWNLOADS_DIR, max_age_days=30)

        exchanges = ["bse", "sse", "szse"] if args.exchange == "all" else [args.exchange]

        for ex in exchanges:
            try:
                report = fetch_report(
                    exchange=ex,
                    days=args.days,
                    download=not args.no_download,
                    parse=not args.no_parse and not args.no_download,
                )
                if args.format == "json":
                    print_json(report)
                else:
                    print_markdown(report, cleaned_files=cleaned)
            except NotImplementedError:
                print(f"⚠ {ex.upper()} not yet implemented, skipping...")
            except Exception as e:
                print(f"✗ Error fetching {ex}: {e}")
                import traceback
                traceback.print_exc()

    elif args.command == "schedule":
        setup_schedule()


if __name__ == "__main__":
    main()
