"""Beijing Stock Exchange (北交所) scraper."""
import re
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..downloader import download_pdf, get_session
from ..parser import parse_pdf
from ..models import FeedbackDocument, ProjectFeedback, FeedbackReport
from .. import config
from .base import ExchangeBase


class BSE(ExchangeBase):
    """北交所 IPO feedback scraper."""

    EXCHANGE = "bse"
    BASE_URL = "https://www.bse.cn"
    LIST_API = "/projectNewsController/infoResult.do"
    DETAIL_API = "/projectNewsController/infoDetailResult.do"

    def _parse_jsonp(self, text: str):
        """Parse JSONP response (wrapped in null(...)) or plain JSON."""
        text = text.strip()
        for pattern in [r"null\((.*)\)", r"callback\((.*)\)"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        return json.loads(text)

    def _classify_doc(self, title: str) -> str:
        """Classify a disclosure document.

        Returns: 'inquiry', 'reply', or 'skip'.
        """
        if "问询函" in title and "回复" not in title:
            return "inquiry"
        if "回复" in title and "会计师" not in title and "律师事务所" not in title:
            return "reply"
        return "skip"

    def fetch_projects(self, days: int = 7) -> FeedbackReport:
        """Fetch IPO projects with feedback from the past N days."""
        import sys
        from concurrent.futures import ThreadPoolExecutor, as_completed

        session = get_session()
        cutoff = datetime.now() - timedelta(days=days)
        date_range = f"{cutoff.strftime('%Y-%m-%d')} ~ {datetime.now().strftime('%Y-%m-%d')}"

        # Step 1: Collect all project items from list API (fast, paginated)
        print(f"📋 Fetching BSE project list...", file=sys.stderr)
        candidate_items = []
        page = 0
        while page < 100:
            resp = session.post(
                f"{self.BASE_URL}{self.LIST_API}",
                data={
                    "page": page,
                    "isNewThree": "1",
                    "sortfield": "updateDate",
                    "sorttype": "desc",
                },
            )
            time.sleep(config.REQUEST_DELAY)
            data = self._parse_jsonp(resp.text)
            items = data[0]["listInfo"]["content"]
            stop = False
            for item in items:
                ts = item["updateDate"]["time"] / 1000
                if datetime.fromtimestamp(ts) < cutoff:
                    stop = True
                    break
                candidate_items.append(item)
            if stop or data[0]["listInfo"]["lastPage"]:
                break
            page += 1

        print(f"📋 Found {len(candidate_items)} projects, fetching details...", file=sys.stderr)

        # Step 2: Fetch details in parallel
        all_projects = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._process_project, session, item, cutoff): item
                for item in candidate_items
            }
            for future in as_completed(futures):
                project = future.result()
                if project:
                    all_projects.append(project)

        # Sort by date descending
        all_projects.sort(key=lambda p: (
            p.inquiry.publish_date if p.inquiry else
            p.reply.publish_date if p.reply else ""
        ), reverse=True)

        print(f"✅ Found {len(all_projects)} projects with feedback documents", file=sys.stderr)
        return FeedbackReport(
            exchange=self.EXCHANGE,
            date_range=date_range,
            projects=all_projects,
        )

    def _process_project(self, session, item: dict, cutoff: datetime) -> ProjectFeedback | None:
        """Process a single project: fetch detail, extract inquiry, reply, and prospectus docs."""
        pid = item["id"]
        company = item["stockName"]
        code = item["stockCode"]

        resp = session.post(
            f"{self.BASE_URL}{self.DETAIL_API}?id={pid}"
        )
        time.sleep(config.REQUEST_DELAY)

        detail = self._parse_jsonp(resp.text)
        wxhfh = detail[0].get("wxhfhInfo", [])
        xxgk = detail[0].get("xxgkInfo", {})

        inquiry_doc = None
        reply_doc = None
        prospectus_doc = None

        # Parse inquiry & reply from wxhfhInfo
        for doc in wxhfh:
            title = doc.get("disclosureTitle", "")
            pub_date = doc.get("publishDate", "")
            if not pub_date:
                continue
            try:
                if datetime.strptime(pub_date, "%Y-%m-%d") < cutoff:
                    continue
            except ValueError:
                continue

            cat = self._classify_doc(title)
            if cat == "skip":
                continue

            pdf_url = f"{self.BASE_URL}{doc.get('destFilePath', '')}"
            exchange_dir = config.DOWNLOADS_DIR / config.EXCHANGE_NAMES[self.EXCHANGE]
            filename = self._make_filename(pub_date, company, title)
            pdf_path = exchange_dir / filename

            fb_doc = FeedbackDocument(
                exchange=self.EXCHANGE,
                company_name=company,
                stock_code=code,
                doc_type=cat,
                title=title,
                publish_date=pub_date,
                pdf_url=pdf_url,
                pdf_path=str(pdf_path),
                content_text="",
            )

            if cat == "inquiry" and inquiry_doc is None:
                inquiry_doc = fb_doc
            elif cat == "reply" and reply_doc is None:
                reply_doc = fb_doc

        # Parse registration draft (注册稿) from GPFXSMS.BHG
        sms = xxgk.get("GPFXSMS", {})
        for doc in sms.get("BHG", []):
            pub_date = doc.get("publishDate", "")
            if not pub_date:
                continue
            try:
                if datetime.strptime(pub_date, "%Y-%m-%d") < cutoff:
                    continue
            except ValueError:
                continue

            title = doc.get("disclosureTitle", "招股说明书（注册稿）")
            pdf_url = f"{self.BASE_URL}{doc.get('destFilePath', '')}"
            exchange_dir = config.DOWNLOADS_DIR / config.EXCHANGE_NAMES[self.EXCHANGE]
            filename = self._make_filename(pub_date, company, title)
            pdf_path = exchange_dir / filename

            prospectus_doc = FeedbackDocument(
                exchange=self.EXCHANGE,
                company_name=company,
                stock_code=code,
                doc_type="prospectus",
                title=title,
                publish_date=pub_date,
                pdf_url=pdf_url,
                pdf_path=str(pdf_path),
                content_text="",
            )
            break  # Take the first (latest) one

        if inquiry_doc is None and reply_doc is None and prospectus_doc is None:
            return None

        return ProjectFeedback(
            company_name=company,
            stock_code=code,
            inquiry=inquiry_doc,
            reply=reply_doc,
            prospectus=prospectus_doc,
        )

    def _make_filename(self, date: str, company: str, title: str) -> str:
        """Generate a clean filename: {date}_{company}_{title}.pdf"""
        # Sanitize title: remove company prefix, keep core description
        clean_title = title
        if ":" in title:
            clean_title = title.split(":", 1)[1]
        if "：" in title:
            clean_title = title.split("：", 1)[1]
        # Remove file-unsafe characters
        clean_title = re.sub(r'[\\/:*?"<>|]', "", clean_title).strip()
        company = re.sub(r'[\\/:*?"<>|]', "", company).strip()
        return f"{date}_{company}_{clean_title}.pdf"

    def download_and_parse(self, report: FeedbackReport, parse_text: bool = True) -> FeedbackReport:
        """Download PDFs first, then parse text. Two separate phases."""
        import sys
        from concurrent.futures import ThreadPoolExecutor, as_completed

        session = get_session()
        docs = []
        for project in report.projects:
            for doc in [project.inquiry, project.reply, project.prospectus]:
                if doc is not None:
                    docs.append(doc)

        # Phase 1: Download all PDFs
        print(f"📥 Phase 1: Downloading {len(docs)} PDFs...", file=sys.stderr)

        def _download(doc):
            pdf_path = Path(doc.pdf_path)
            if not pdf_path.exists():
                success = download_pdf(doc.pdf_url, pdf_path, session)
                if not success:
                    doc.content_text = "[Download failed]"

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_download, doc) for doc in docs]
            for i, future in enumerate(as_completed(futures), 1):
                future.result()
                print(f"  ✓ [{i}/{len(docs)}] downloaded", file=sys.stderr)

        # Phase 2: Parse all downloaded PDFs
        if parse_text:
            print(f"📄 Phase 2: Parsing {len(docs)} PDFs...", file=sys.stderr)
            for i, doc in enumerate(docs, 1):
                pdf_path = Path(doc.pdf_path)
                if pdf_path.exists() and not doc.content_text.startswith("["):
                    doc.content_text = parse_pdf(pdf_path, max_chars=config.PDF_TEXT_LIMIT)
                    print(f"  ✓ [{i}/{len(docs)}] parsed", file=sys.stderr)

        return report
