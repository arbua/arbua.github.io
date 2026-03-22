#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import uuid
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

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


def categorize(title: str, journal: str, abstract: str) -> tuple[str, str]:
    text = f"{title} {journal} {abstract}".lower()
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
        "ai",
    ]
    if any(keyword in text for keyword in cs_keywords):
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
    text = re.sub(r"[^A-Za-z0-9 ]+", "", title).strip()[:36] or f"Paper {index}"
    encoded = requests.utils.quote(f"Paper {index}: {text}")
    return f"https://placehold.co/600x340/{bg}/{fg}?text={encoded}"


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
    if not re.match(r"^paper-\d+\.(jpg|jpeg|png|webp)$", candidate.name, flags=re.IGNORECASE):
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


def safe_batch_rename(repo_root: Path, rename_pairs: list[tuple[Path, Path]]) -> None:
    effective_pairs: list[tuple[Path, Path]] = []
    seen_src: set[Path] = set()
    for src_rel, dst_rel in rename_pairs:
        src_abs = (repo_root / src_rel).resolve()
        dst_abs = (repo_root / dst_rel).resolve()
        if src_abs == dst_abs:
            continue
        if src_abs in seen_src:
            continue
        if not src_abs.exists():
            continue
        seen_src.add(src_abs)
        effective_pairs.append((src_rel, dst_rel))

    if not effective_pairs:
        return

    moving_sources = {(repo_root / src_rel).resolve() for src_rel, _ in effective_pairs}
    temp_moves: list[tuple[Path, Path, Path]] = []

    for src_rel, dst_rel in effective_pairs:
        src_abs = (repo_root / src_rel).resolve()
        temp_name = f"{src_abs.name}.tmp.{uuid.uuid4().hex}"
        temp_abs = src_abs.with_name(temp_name)
        src_abs.rename(temp_abs)
        temp_moves.append((temp_abs, src_abs, (repo_root / dst_rel).resolve()))

    for temp_abs, original_abs, dst_abs in temp_moves:
        dst_abs.parent.mkdir(parents=True, exist_ok=True)
        if dst_abs.exists() and dst_abs not in moving_sources:
            temp_abs.rename(original_abs)
            continue
        temp_abs.rename(dst_abs)


def resolve_publication_images(
    publications: list[Publication],
    image_overrides: dict[str, str],
    repo_root: Path,
) -> None:
    rename_pairs: list[tuple[Path, Path]] = []
    total_count = len(publications)

    for position, publication in enumerate(publications, start=1):
        publication_number = publication_number_for_position(total_count=total_count, position=position)
        key = publication_key(publication.title, publication.year)
        override = image_overrides.get(key, "")
        local_override = parse_local_paper_image_path(override)
        if not local_override:
            continue

        source_abs = repo_root / local_override
        if not source_abs.exists():
            continue

        desired_rel = PAPERS_DIR / f"paper-{publication_number}{local_override.suffix.lower()}"
        if local_override != desired_rel:
            rename_pairs.append((local_override, desired_rel))

    safe_batch_rename(repo_root=repo_root, rename_pairs=rename_pairs)
    indexed_local_images = discover_local_images(repo_root=repo_root)

    for position, publication in enumerate(publications, start=1):
        publication_number = publication_number_for_position(total_count=total_count, position=position)
        key = publication_key(publication.title, publication.year)
        override = image_overrides.get(key, "")
        local_override = parse_local_paper_image_path(override)

        if local_override:
            desired_rel = PAPERS_DIR / f"paper-{publication_number}{local_override.suffix.lower()}"
            if (repo_root / desired_rel).exists():
                publication.image_src = f"./{desired_rel.as_posix()}"
                continue

        indexed_local = indexed_local_images.get(publication_number)
        if indexed_local and (repo_root / indexed_local).exists():
            publication.image_src = f"./{indexed_local.as_posix()}"
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


def publication_link(pub: dict, doi: str) -> str:
    for key in ["pub_url", "eprint_url", "url_scholarbib"]:
        value = pub.get(key, "")
        if value:
            return value
    if doi:
        return f"https://doi.org/{doi}"
    return "#"


def fetch_scholar_publications(
    user_id: str,
    max_items: int,
    image_overrides: dict[str, str],
    repo_root: Path,
) -> list[Publication]:
    author = scholarly.search_author_id(user_id)
    author = scholarly.fill(author, sections=["publications"])
    publications = author.get("publications", [])[:max_items]

    unique_tracker: set[str] = set()
    results: list[Publication] = []

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

        dedupe_key = doi.lower() if doi else f"{title.lower()}::{year or 'unknown'}"
        if dedupe_key in unique_tracker:
            continue
        unique_tracker.add(dedupe_key)

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

        category_slug, category_label = categorize(title=title, journal=journal, abstract=abstract)
        summary = generate_summary(abstract=abstract, title=title)
        link = publication_link(full_pub, doi)

        publication = Publication(
            title=title,
            year=year,
            authors=authors,
            journal=journal,
            summary=summary,
            category_slug=category_slug,
            category_label=category_label,
            image_src="",
            link=link,
            doi=doi,
            abstract=abstract,
        )
        results.append(publication)

    results.sort(key=lambda item: (item.year or 0, item.title.lower()), reverse=True)
    resolve_publication_images(publications=results, image_overrides=image_overrides, repo_root=repo_root)
    return results


def format_title(title: str, year: Optional[int]) -> str:
    if year:
        return f"{title}. ({year})"
    return title


def render_publications_html(publications: list[Publication]) -> str:
    lines: list[str] = []
    total_count = len(publications)
    for position, publication in enumerate(publications, start=1):
        publication_number = publication_number_for_position(total_count=total_count, position=position)
        lines.extend(
            [
                f"            <!-- Publication {publication_number} -->",
                f"            <li class=\"project-item active\" data-filter-item data-category=\"{html.escape(publication.category_slug)}\">",
                "              <a href=\"#\" class=\"publication-trigger\">",
                "                <figure class=\"project-img\">",
                "                  <div class=\"project-item-icon-box\">",
                "                    <ion-icon name=\"eye-outline\"></ion-icon>",
                "                  </div>",
                f"                  <img src=\"{html.escape(publication.image_src)}\" alt=\"Publication {publication_number}\" loading=\"lazy\">",
                "                </figure>",
                f"                <h3 class=\"project-title\">{html.escape(format_title(publication.title, publication.year))}</h3>",
                f"                <p class=\"project-category\" style=\"display: none;\">{html.escape(publication.category_label)}</p>",
                "              </a>",
                "              <div class=\"project-summary\" style=\"display: none;\">",
                "                <p>",
                "                  <strong>Authors:</strong><br>",
                f"                  {html.escape(publication.authors)}<br><br>",
                "                  <strong>Journal:</strong><br>",
                f"                  {html.escape(publication.journal)}<br><br>",
                "                  <strong>Summary:</strong><br>",
                f"                  {html.escape(publication.summary)}",
                "                </p>",
                f"                <a href=\"{html.escape(publication.link)}\" target=\"_blank\">View Publication</a>",
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

    publications = fetch_scholar_publications(
        user_id=args.scholar_user,
        max_items=args.max_items,
        image_overrides=image_overrides,
        repo_root=repo_root,
    )
    if not publications:
        raise RuntimeError("No publications were fetched from Google Scholar.")

    publications_html = render_publications_html(publications)
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
