"""Data models for IPO feedback documents."""
from dataclasses import dataclass, field


@dataclass
class FeedbackDocument:
    """A single disclosure document (inquiry letter or reply)."""
    exchange: str           # "bse" / "sse" / "szse"
    company_name: str       # Company short name
    stock_code: str         # Stock code
    doc_type: str           # "inquiry" or "reply"
    title: str              # Document title
    publish_date: str       # Publication date YYYY-MM-DD
    pdf_url: str            # PDF download URL
    pdf_path: str           # Local save path
    content_text: str = ""  # Extracted text content


@dataclass
class ProjectFeedback:
    """Feedback documents for a single IPO project."""
    company_name: str
    stock_code: str
    inquiry: FeedbackDocument | None = None   # 审核问询函
    reply: FeedbackDocument | None = None     # 问询回复
    prospectus: FeedbackDocument | None = None  # 招股说明书注册稿


@dataclass
class FeedbackReport:
    """A collection of feedback from one exchange."""
    exchange: str
    date_range: str
    projects: list[ProjectFeedback] = field(default_factory=list)
