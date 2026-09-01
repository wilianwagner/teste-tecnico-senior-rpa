import re

from bs4 import BeautifulSoup, Tag

from app.core.exceptions import CrawlerError
from app.schemas.crawl import HockeyTeamData

_PAGE_NUM_RE = re.compile(r"page_num=(\d+)")


def parse_teams(html: str) -> list[HockeyTeamData]:
    """Extract every team row from a listing page.

    Empty OT-losses cells become None (pre-2000 seasons have no such stat).
    A row missing cells or holding non-numeric values raises CrawlerError:
    failing loudly beats persisting an incomplete dataset.
    """
    soup = BeautifulSoup(html, "lxml")
    return [_parse_row(row) for row in soup.select("tr.team")]


def parse_total_pages(html: str) -> int:
    """Read the highest page number from the pagination block; 1 when absent."""
    soup = BeautifulSoup(html, "lxml")
    pagination = soup.select_one("ul.pagination")
    if pagination is None:
        return 1

    pages = [
        int(match.group(1))
        for link in pagination.select("a[href]")
        if (match := _PAGE_NUM_RE.search(str(link["href"])))
    ]
    return max(pages, default=1)


def _parse_row(row: Tag) -> HockeyTeamData:
    try:
        return HockeyTeamData(
            team_name=_cell_text(row, "td.name"),
            year=int(_cell_text(row, "td.year")),
            wins=int(_cell_text(row, "td.wins")),
            losses=int(_cell_text(row, "td.losses")),
            ot_losses=_optional_int(_cell_text(row, "td.ot-losses")),
            win_pct=float(_cell_text(row, "td.pct")),
            goals_for=int(_cell_text(row, "td.gf")),
            goals_against=int(_cell_text(row, "td.ga")),
            goal_diff=int(_cell_text(row, "td.diff")),
        )
    except (ValueError, CrawlerError) as exc:
        raise CrawlerError(f"Malformed hockey team row: {exc}") from exc


def _cell_text(row: Tag, selector: str) -> str:
    cell = row.select_one(selector)
    if cell is None:
        raise CrawlerError(f"Missing cell {selector!r}")
    return cell.get_text(strip=True)


def _optional_int(value: str) -> int | None:
    return int(value) if value else None
