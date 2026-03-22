#!/usr/bin/env python3
import argparse
import hashlib
import html
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from scholarly import scholarly


START_MARKER = "<!-- PUBLICATIONS:START -->"
END_MARKER = "<!-- PUBLICATIONS:END -->"
DEFAULT_SCHOLAR_USER = "WwS3uCwAAAAJ"
PAPERS_DIR = Path("assets/images/papers")
LOCAL_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
class Publication:
    title: str
    year: Optional[int]
    authors: str
    journal: str
    summary: str
    category_slug: str
    category_label: str
    image_src: str
    link: str
    journal_link: str
    arxiv_link: str
    doi: str
    abstract: str


def publication_key(title: str, year: Optional[int]) -> str:
    normalized = re.sub(r"\s+", " ", title or "").strip().lower()
    return f"{normalized}::{year or 'unknown'}"


def publication_number_for_position(total_count: int, position: int) -> int:
    return total_count - position + 1


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def split_authors(raw_authors: str) -> str:
    if not raw_authors:
        return "Unknown"
    normalized = raw_authors.replace(" and ", ", ")
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    return ", ".join(parts) if parts else "Unknown"


def extract_doi(*values: str) -> str:
    doi_pattern = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", flags=re.IGNORECASE)
    for value in values:
        if not value:
            continue
        match = doi_pattern.search(value)
        if match:
            return match.group(0).rstrip(".")
    return ""


def parse_year(value: str) -> Optional[int]:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    if not match:
        return None
    return int(match.group(0))


def decode_openalex_abstract(abstract_index: dict) -> str:
    if not abstract_index:
        return ""
    positions: dict[int, str] = {}
    for word, location_list in abstract_index.items():
        for location in location_list:
            positions[location] = word
    return " ".join(positions[index] for index in sorted(positions)).strip()


def get_openalex_journal_name(payload: dict) -> str:
    primary_location = payload.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return (source.get("display_name") or "").strip()


def openalex_lookup(doi: str, title: str, timeout: int = 15) -> tuple[str, str]:
    try:
        if doi:
            doi_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
            response = requests.get(doi_url, timeout=timeout)
            if response.ok:
                payload = response.json()
                journal = get_openalex_journal_name(payload)
                abstract = decode_openalex_abstract(payload.get("abstract_inverted_index", {}))
                return abstract, journal

        if title:
            search_url = "https://api.openalex.org/works"
            response = requests.get(
                search_url,
                params={"search": title, "per-page": 1},
                timeout=timeout,
            )
            if response.ok:
                payload = response.json()
                results = payload.get("results", [])
                if results:
                    first = results[0]
                    journal = get_openalex_journal_name(first)
                    abstract = decode_openalex_abstract(first.get("abstract_inverted_index", {}))
                    return abstract, journal
    except requests.RequestException:
        return "", ""

    return "", ""


def configure_network_from_env() -> None:
    proxy_http = os.getenv("SCHOLARLY_PROXY_HTTP", "").strip()
    proxy_https = os.getenv("SCHOLARLY_PROXY_HTTPS", "").strip()
    if proxy_http and not os.getenv("HTTP_PROXY"):
        os.environ["HTTP_PROXY"] = proxy_http
    if proxy_https and not os.getenv("HTTPS_PROXY"):
        os.environ["HTTPS_PROXY"] = proxy_https


def generate_summary(abstract: str, title: str) -> str:
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", abstract or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned:
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        picked = " ".join(sentences[:2]).strip()
        if len(picked) > 420:
            picked = picked[:417].rsplit(" ", 1)[0] + "..."
        return picked

    base = f"This publication presents {title.lower()} and reports its main clinical and technical implications."
    if len(base) > 420:
        base = base[:417].rsplit(" ", 1)[0] + "..."
    return base


def categorize(title: str, journal: str, abstract: str, link: str = "") -> tuple[str, str]:
    text = f"{title} {journal} {abstract} {link}".lower()

    book_chapter_keywords = [
        "book chapter",
        "springer.com/chapter",
        "atlas of virtual surgical planning",
        "(eds)",
        " in: ",
    ]
    if any(keyword in text for keyword in book_chapter_keywords):
        return "book chapters", "Book Chapters"

    cs_keywords = [
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "computer vision",
        "diffusion",
        "segment",
        "dataset",
        "algorithm",
        "text-to-image",
        "multimodal",
        "benchmark",
        "model",
        "architecture",
        "prompt",
        "ai",
    ]

    clinical_keywords = [
        "surgery",
        "surgical",
        "clinical",
        "trial",
        "patient",
        "cancer",
        "gynecological",
        "colorectal",
        "sentinel",
        "lymph",
        "workflow",
        "hysterectomy",
        "endometrial",
        "cervical",
    ]

    cs_score = sum(1 for keyword in cs_keywords if keyword in text)
    clinical_score = sum(1 for keyword in clinical_keywords if keyword in text)

    journal_text = (journal or "").lower()
    if any(token in journal_text for token in ["arxiv", "pattern recognition", "computer", "ieee", "acm"]):
        cs_score += 2
    if any(token in journal_text for token in ["surgery", "oncology", "cancer", "clinical", "gynecological", "journal of"]):
        clinical_score += 2

    if clinical_score > cs_score:
        return "clinical", "Clinical"
    if cs_score > 0:
        return "computer science", "Computer Science"
    return "clinical", "Clinical"


def placeholder_image(index: int, title: str) -> str:
    palettes = [
        ("6b7280", "f3f4f6"),
        ("0f766e", "f0fdfa"),
        ("1d4ed8", "eff6ff"),
        ("7c3aed", "f5f3ff"),
        ("b45309", "fffbeb"),
        ("be123c", "fff1f2"),
        ("374151", "f9fafb"),
        ("065f46", "ecfdf5"),
    ]
    bg, fg = palettes[(index - 1) % len(palettes)]
    text = re.sub(r"[^A-Za-z0-9 ]+", "", title).strip()[:36] or "Publication"
    encoded = requests.utils.quote(text)
    return f"https://placehold.co/600x340/{bg}/{fg}?text={encoded}"


def is_arxiv_url(url: str) -> bool:
    value = (url or "").lower()
    return "arxiv.org" in value


def is_preprint_venue(journal: str) -> bool:
    value = (journal or "").lower()
    preprint_tokens = [
        "arxiv",
        "preprint",
        "biorxiv",
        "medrxiv",
        "unspecified venue",
    ]
    return any(token in value for token in preprint_tokens)


def normalize_title_for_merge(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def extract_publication_links(pub: dict, doi: str) -> tuple[str, str, str]:
    candidates: list[str] = []
    for key in ["pub_url", "eprint_url", "url_scholarbib"]:
        value = (pub.get(key) or "").strip()
        if value and value.startswith("http"):
            candidates.append(value)

    if doi:
        candidates.append(f"https://doi.org/{doi}")

    deduped_candidates = list(dict.fromkeys(candidates))

    arxiv_link = ""
    journal_link = ""
    for candidate in deduped_candidates:
        if is_arxiv_url(candidate):
            if not arxiv_link:
                arxiv_link = candidate
            continue
        if not journal_link:
            journal_link = candidate

    primary_link = journal_link or arxiv_link or "#"
    return primary_link, journal_link, arxiv_link


def choose_preferred_publication(first: Publication, second: Publication) -> tuple[Publication, Publication]:
    def quality_score(item: Publication) -> int:
        score = 0
        if not is_preprint_venue(item.journal):
            score += 3
        if item.journal_link:
            score += 2
        if item.doi:
            score += 2
        if item.abstract:
            score += 1
        return score

    first_score = quality_score(first)
    second_score = quality_score(second)
    if second_score > first_score:
        return second, first
    if first_score > second_score:
        return first, second

    first_year = first.year or 0
    second_year = second.year or 0
    if second_year > first_year:
        return second, first
    return first, second


def merge_publications(publications: list[Publication]) -> list[Publication]:
    merged_by_key: dict[str, Publication] = {}

    for publication in publications:
        key = normalize_title_for_merge(publication.title)
        if not key:
            key = publication_key(publication.title, publication.year)

        if key not in merged_by_key:
            merged_by_key[key] = publication
            continue

        preferred, secondary = choose_preferred_publication(merged_by_key[key], publication)

        merged_item = Publication(
            title=preferred.title if len(preferred.title) >= len(secondary.title) else secondary.title,
            year=max(preferred.year or 0, secondary.year or 0) or None,
            authors=preferred.authors if len(preferred.authors) >= len(secondary.authors) else secondary.authors,
            journal=preferred.journal if not is_preprint_venue(preferred.journal) else secondary.journal,
            summary=preferred.summary if len(preferred.summary) >= len(secondary.summary) else secondary.summary,
            category_slug=preferred.category_slug,
            category_label=preferred.category_label,
            image_src=preferred.image_src,
            link=preferred.link,
            journal_link=preferred.journal_link or secondary.journal_link,
            arxiv_link=preferred.arxiv_link or secondary.arxiv_link,
            doi=preferred.doi or secondary.doi,
            abstract=preferred.abstract if len(preferred.abstract) >= len(secondary.abstract) else secondary.abstract,
        )

        if not merged_item.journal or is_preprint_venue(merged_item.journal):
            if secondary.journal and not is_preprint_venue(secondary.journal):
                merged_item.journal = secondary.journal

        if merged_item.journal_link:
            merged_item.link = merged_item.journal_link
        elif merged_item.arxiv_link:
            merged_item.link = merged_item.arxiv_link
        elif merged_item.doi:
            merged_item.link = f"https://doi.org/{merged_item.doi}"

        merged_by_key[key] = merged_item

    return list(merged_by_key.values())


def parse_local_paper_image_path(image_src: str) -> Optional[Path]:
    normalized = (image_src or "").strip()
    if not normalized:
        return None

    if normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/"):
        normalized = normalized[1:]

    candidate = Path(normalized)
    if candidate.parent.as_posix() != PAPERS_DIR.as_posix():
        return None
    if candidate.suffix.lower() not in LOCAL_IMAGE_EXTENSIONS:
        return None

    return Path(candidate.as_posix())


def discover_local_images(repo_root: Path) -> dict[int, Path]:
    papers_abs = repo_root / PAPERS_DIR
    if not papers_abs.exists():
        return {}

    by_index: dict[int, Path] = {}
    for path in sorted(papers_abs.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in LOCAL_IMAGE_EXTENSIONS:
            continue
        match = re.match(r"^paper-(\d+)\.[A-Za-z0-9]+$", path.name)
        if not match:
            continue
        index = int(match.group(1))
        relative = Path(path.relative_to(repo_root).as_posix())
        if index not in by_index:
            by_index[index] = relative
    return by_index


def extract_og_or_twitter_image(page_html: str, base_url: str) -> str:
    patterns = [
        r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
        r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page_html, flags=re.IGNORECASE)
        if match:
            return urljoin(base_url, match.group(1).strip())
    return ""


def infer_image_extension(image_url: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"

    parsed = Path(image_url.split("?", 1)[0])
    suffix = parsed.suffix.lower()
    if suffix in LOCAL_IMAGE_EXTENSIONS:
        return suffix
    return ".jpg"


def auto_download_publication_image(
    publication: Publication,
    repo_root: Path,
    publication_number: int,
    timeout: int = 12,
) -> str:
    candidate_pages = [publication.journal_link, publication.link, publication.arxiv_link]
    candidate_pages = [page for page in candidate_pages if page and page.startswith("http")]

    if not candidate_pages:
        return ""

    publication_hash = hashlib.sha1(publication_key(publication.title, publication.year).encode("utf-8")).hexdigest()[:10]
    base_name = f"paper-auto-{publication_hash}"
    papers_abs = repo_root / PAPERS_DIR
    papers_abs.mkdir(parents=True, exist_ok=True)

    existing_matches = list(papers_abs.glob(f"{base_name}.*"))
    for existing in existing_matches:
        if existing.suffix.lower() in LOCAL_IMAGE_EXTENSIONS:
            return f"./{existing.relative_to(repo_root).as_posix()}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    }

    for page_url in candidate_pages:
        try:
            page_response = requests.get(page_url, timeout=timeout, headers=headers)
            if not page_response.ok:
                continue

            image_url = extract_og_or_twitter_image(page_response.text, page_url)
            if not image_url or not image_url.startswith("http"):
                continue

            image_response = requests.get(image_url, timeout=timeout, headers=headers)
            if not image_response.ok:
                continue

            content_type = image_response.headers.get("Content-Type", "")
            if content_type and not content_type.lower().startswith("image/"):
                continue

            extension = infer_image_extension(image_url, content_type)
            destination_rel = PAPERS_DIR / f"{base_name}{extension}"
            destination_abs = repo_root / destination_rel

            if destination_abs.exists():
                return f"./{destination_rel.as_posix()}"

            destination_abs.write_bytes(image_response.content)
            return f"./{destination_rel.as_posix()}"
        except requests.RequestException:
            continue

    return ""


def apply_image_to_preserved_card(card_html: str, resolved_image_src: str, repo_root: Path) -> str:
    if not resolved_image_src or "placehold.co" in resolved_image_src:
        return card_html

    image_src_pattern = re.compile(r'(<img\s+[^>]*src=")([^"]+)("[^>]*>)', flags=re.IGNORECASE)
    match = image_src_pattern.search(card_html)
    if not match:
        return card_html

    current_src = match.group(2)
    should_replace = "placehold.co" in current_src

    current_local_path = parse_local_paper_image_path(current_src)
    if current_local_path and not (repo_root / current_local_path).exists():
        should_replace = True

    if not should_replace:
        return card_html

    return image_src_pattern.sub(rf'\1{resolved_image_src}\3', card_html, count=1)


def resolve_publication_images(
    publications: list[Publication],
    image_overrides: dict[str, str],
    repo_root: Path,
    auto_fetch_images: bool,
) -> None:
    total_count = len(publications)
    indexed_local_images = discover_local_images(repo_root=repo_root)

    for position, publication in enumerate(publications, start=1):
        publication_number = publication_number_for_position(total_count=total_count, position=position)
        key = publication_key(publication.title, publication.year)
        override = image_overrides.get(key, "")
        local_override = parse_local_paper_image_path(override)

        if local_override:
            if (repo_root / local_override).exists():
                publication.image_src = f"./{local_override.as_posix()}"
                continue

        indexed_local = indexed_local_images.get(publication_number)
        if indexed_local and (repo_root / indexed_local).exists():
            publication.image_src = f"./{indexed_local.as_posix()}"
            continue

        if auto_fetch_images:
            auto_image = auto_download_publication_image(
                publication=publication,
                repo_root=repo_root,
                publication_number=publication_number,
            )
            if auto_image:
                publication.image_src = auto_image
                continue

        publication.image_src = placeholder_image(publication_number, publication.title)


def parse_formatted_title(value: str) -> tuple[str, Optional[int]]:
    text = re.sub(r"\s+", " ", value or "").strip()
    match = re.match(r"^(.*)\.\s\((\d{4})\)$", text)
    if not match:
        return text, None
    return match.group(1).strip(), int(match.group(2))


def existing_image_overrides(index_html_path: Path) -> dict[str, str]:
    if not index_html_path.exists():
        return {}

    content = index_html_path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        return {}

    _, remainder = content.split(START_MARKER, 1)
    block, _ = remainder.split(END_MARKER, 1)

    pattern = re.compile(
        r'<li class="project-item active"[^>]*>.*?<img src="([^"]+)"[^>]*>.*?<h3 class="project-title">(.*?)</h3>',
        flags=re.DOTALL,
    )

    overrides: dict[str, str] = {}
    for image_src, title_markup in pattern.findall(block):
        parsed_title = re.sub(r"<[^>]+>", "", title_markup)
        title, year = parse_formatted_title(parsed_title)
        if "placehold.co" in image_src:
            continue
        overrides[publication_key(title, year)] = image_src

    return overrides


def existing_publication_cards(index_html_path: Path) -> dict[str, str]:
    if not index_html_path.exists():
        return {}

    content = index_html_path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        return {}

    _, remainder = content.split(START_MARKER, 1)
    block, _ = remainder.split(END_MARKER, 1)

    card_pattern = re.compile(r'(<li class="project-item active"[^>]*>[\s\S]*?</li>)', flags=re.DOTALL)
    title_pattern = re.compile(r'<h3 class="project-title">(.*?)</h3>', flags=re.DOTALL)

    cards: dict[str, str] = {}
    for card_html in card_pattern.findall(block):
        title_match = title_pattern.search(card_html)
        if not title_match:
            continue

        parsed_title = re.sub(r"<[^>]+>", "", title_match.group(1))
        title, year = parse_formatted_title(parsed_title)
        cards[publication_key(title, year)] = card_html.strip()

    return cards


def fetch_scholar_publications(
    user_id: str,
    max_items: int,
    image_overrides: dict[str, str],
    repo_root: Path,
    auto_fetch_images: bool,
) -> list[Publication]:
    author = scholarly.search_author_id(user_id)
    author = scholarly.fill(author, sections=["publications"])
    publications = author.get("publications", [])[:max_items]

    raw_results: list[Publication] = []

    for rank, pub_stub in enumerate(publications, start=1):
        full_pub = scholarly.fill(pub_stub)
        bib = full_pub.get("bib", {})

        title = (bib.get("title") or "Untitled publication").strip()
        year = parse_year(str(bib.get("pub_year") or bib.get("year") or ""))
        raw_authors = bib.get("author", "")
        authors = split_authors(raw_authors)

        journal = (
            (bib.get("journal") or "").strip()
            or (bib.get("venue") or "").strip()
            or (bib.get("conference") or "").strip()
            or (bib.get("booktitle") or "").strip()
        )

        doi = extract_doi(
            bib.get("doi", ""),
            full_pub.get("pub_url", ""),
            full_pub.get("eprint_url", ""),
            full_pub.get("url_scholarbib", ""),
        )

        abstract = (bib.get("abstract") or "").strip()
        openalex_abstract = ""
        openalex_journal = ""
        if not abstract or not journal:
            openalex_abstract, openalex_journal = openalex_lookup(doi=doi, title=title)

        if not abstract and openalex_abstract:
            abstract = openalex_abstract
        if not journal and openalex_journal:
            journal = openalex_journal

        if not journal:
            journal = "Preprint / Unspecified Venue"

        primary_link, journal_link, arxiv_link = extract_publication_links(pub=full_pub, doi=doi)

        summary = generate_summary(abstract=abstract, title=title)

        publication = Publication(
            title=title,
            year=year,
            authors=authors,
            journal=journal,
            summary=summary,
            category_slug="",
            category_label="",
            image_src="",
            link=primary_link,
            journal_link=journal_link,
            arxiv_link=arxiv_link,
            doi=doi,
            abstract=abstract,
        )

        publication.category_slug, publication.category_label = categorize(
            title=publication.title,
            journal=publication.journal,
            abstract=publication.abstract,
            link=publication.link,
        )
        raw_results.append(publication)

    results = merge_publications(raw_results)

    for publication in results:
        publication.category_slug, publication.category_label = categorize(
            title=publication.title,
            journal=publication.journal,
            abstract=publication.abstract,
            link=publication.link,
        )

    results.sort(key=lambda item: (item.year or 0, item.title.lower()), reverse=True)
    resolve_publication_images(
        publications=results,
        image_overrides=image_overrides,
        repo_root=repo_root,
        auto_fetch_images=auto_fetch_images,
    )
    return results


def format_title(title: str, year: Optional[int]) -> str:
    if year:
        return f"{title}. ({year})"
    return title


def render_publications_html(
    publications: list[Publication],
    existing_cards: dict[str, str],
    preserve_existing_cards: bool,
    repo_root: Path,
) -> str:
    lines: list[str] = []
    total_count = len(publications)
    for position, publication in enumerate(publications, start=1):
        publication_number = publication_number_for_position(total_count=total_count, position=position)
        key = publication_key(publication.title, publication.year)

        if preserve_existing_cards and key in existing_cards:
            preserved_card = apply_image_to_preserved_card(
                card_html=existing_cards[key],
                resolved_image_src=publication.image_src,
                repo_root=repo_root,
            )
            lines.extend(
                [
                    f"            <!-- Publication {publication_number} -->",
                    f"            {preserved_card}",
                    "",
                ]
            )
            continue

        summary_id = f"publication-summary-{publication_number}"
        cta_lines: list[str] = []
        seen_links: set[str] = set()

        def add_cta(url: str, label: str) -> None:
            normalized = (url or "").strip()
            if not normalized or normalized == "#" or normalized in seen_links:
                return
            seen_links.add(normalized)
            cta_lines.append(
                f"                <a href=\"{html.escape(normalized)}\" target=\"_blank\" rel=\"noopener noreferrer\">{html.escape(label)}</a>"
            )

        add_cta(publication.journal_link, "View Journal")
        if publication.arxiv_link and publication.arxiv_link != publication.journal_link:
            add_cta(publication.arxiv_link, "View arXiv")
        add_cta(publication.link, "View Publication")

        lines.extend(
            [
                f"            <!-- Publication {publication_number} -->",
                f"            <li class=\"project-item active\" data-filter-item data-category=\"{html.escape(publication.category_slug)}\">",
                f"              <a href=\"#\" class=\"publication-trigger\" role=\"button\" aria-expanded=\"false\" aria-controls=\"{summary_id}\">",
                "                <figure class=\"project-img\">",
                "                  <div class=\"project-item-icon-box\">",
                "                    <ion-icon name=\"eye-outline\"></ion-icon>",
                "                  </div>",
                f"                  <img src=\"{html.escape(publication.image_src)}\" alt=\"Publication {publication_number}\" loading=\"lazy\">",
                "                </figure>",
                f"                <h3 class=\"project-title\">{html.escape(format_title(publication.title, publication.year))}</h3>",
                f"                <p class=\"project-category\" style=\"display: none;\">{html.escape(publication.category_label)}</p>",
                "              </a>",
                f"              <div class=\"project-summary\" id=\"{summary_id}\" hidden style=\"display: none;\">",
                "                <p>",
                "                  <strong>Authors:</strong><br>",
                f"                  {html.escape(publication.authors)}<br><br>",
                "                  <strong>Journal:</strong><br>",
                f"                  {html.escape(publication.journal)}<br><br>",
                "                  <strong>Summary:</strong><br>",
                f"                  {html.escape(publication.summary)}",
                "                </p>",
            ]
        )

        lines.extend(cta_lines)
        lines.extend(
            [
                "              </div>",
                "            </li>",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def replace_publications_block(index_html_path: Path, publications_html: str) -> None:
    content = index_html_path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        raise RuntimeError("Publication markers were not found in index.html.")

    before, remainder = content.split(START_MARKER, 1)
    _, after = remainder.split(END_MARKER, 1)

    new_content = f"{before}{START_MARKER}\n{publications_html}\n\n            {END_MARKER}{after}"
    index_html_path.write_text(new_content, encoding="utf-8")


def write_publications_json(publications: list[Publication], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(publications),
        "publications": [asdict(item) for item in publications],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def commit_and_push(repo_root: Path, files: list[Path], message: str, should_push: bool) -> str:
    add_cmd = ["git", "add"] + [str(file.relative_to(repo_root)) for file in files]
    add_result = run_command(add_cmd, cwd=repo_root)
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stderr.strip() or "Failed to stage files.")

    diff_result = run_command(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
    if diff_result.returncode == 0:
        return "No changes detected; nothing to commit."

    commit_result = run_command(["git", "commit", "-m", message], cwd=repo_root)
    if commit_result.returncode != 0:
        raise RuntimeError(commit_result.stderr.strip() or "Failed to commit changes.")

    if should_push:
        branch_result = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
        if branch_result.returncode != 0:
            raise RuntimeError(branch_result.stderr.strip() or "Failed to determine current branch.")
        branch = branch_result.stdout.strip() or "main"

        push_result = run_command(["git", "push", "origin", branch], cwd=repo_root)
        if push_result.returncode != 0:
            raise RuntimeError(push_result.stderr.strip() or "Failed to push changes.")

        return f"Committed and pushed to origin/{branch}."

    return "Committed locally (push skipped)."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync publications from Google Scholar into partials/publications.html and optionally push changes."
    )
    parser.add_argument("--scholar-user", default=DEFAULT_SCHOLAR_USER, help="Google Scholar user ID")
    parser.add_argument("--max-items", type=int, default=40, help="Maximum number of publications to fetch")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Path to repository root",
    )
    parser.add_argument("--skip-git", action="store_true", help="Do not commit or push changes")
    parser.add_argument("--no-push", action="store_true", help="Commit only; do not push")
    parser.add_argument(
        "--no-preserve-existing",
        action="store_true",
        help="Regenerate all publication cards instead of preserving existing card HTML for known publications",
    )
    parser.add_argument(
        "--no-auto-image-fetch",
        action="store_true",
        help="Disable automatic remote image retrieval for publications without local images",
    )
    parser.add_argument(
        "--commit-message",
        default=f"chore(publications): sync scholar {datetime.utcnow().date().isoformat()}",
        help="Commit message for publication sync",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_network_from_env()
    repo_root = Path(args.repo_root).resolve()
    publications_html_path = repo_root / "partials" / "publications.html"
    data_json_path = repo_root / "data" / "publications.json"
    image_overrides = existing_image_overrides(index_html_path=publications_html_path)
    existing_cards = existing_publication_cards(index_html_path=publications_html_path)

    publications = fetch_scholar_publications(
        user_id=args.scholar_user,
        max_items=args.max_items,
        image_overrides=image_overrides,
        repo_root=repo_root,
        auto_fetch_images=not args.no_auto_image_fetch,
    )
    if not publications:
        raise RuntimeError("No publications were fetched from Google Scholar.")

    publications_html = render_publications_html(
        publications=publications,
        existing_cards=existing_cards,
        preserve_existing_cards=not args.no_preserve_existing,
        repo_root=repo_root,
    )
    replace_publications_block(index_html_path=publications_html_path, publications_html=publications_html)
    write_publications_json(publications=publications, output_path=data_json_path)

    print(f"Updated {publications_html_path}")
    print(f"Wrote {data_json_path}")

    if args.skip_git:
        print("Skipping git commit/push as requested.")
        return

    status = commit_and_push(
        repo_root=repo_root,
        files=[publications_html_path, data_json_path],
        message=args.commit_message,
        should_push=not args.no_push,
    )
    print(status)


if __name__ == "__main__":
    main()
