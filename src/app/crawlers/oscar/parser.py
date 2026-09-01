from bs4 import BeautifulSoup, Tag

from app.core.exceptions import CrawlerError
from app.schemas.crawl import OscarFilmData


def parse_films(html: str, year: int) -> list[OscarFilmData]:
    soup = BeautifulSoup(html, "lxml")
    return [_parse_row(row, year) for row in soup.select("tr.film")]


def _parse_row(row: Tag, year: int) -> OscarFilmData:
    try:
        return OscarFilmData(
            year=year,
            title=_cell_text(row, "td.film-title"),
            nominations=int(_cell_text(row, "td.film-nominations")),
            awards=int(_cell_text(row, "td.film-awards")),
            best_picture=_has_best_picture_flag(row),
        )
    except (ValueError, CrawlerError) as exc:
        raise CrawlerError(f"Malformed oscar film row: {exc}") from exc


def _cell_text(row: Tag, selector: str) -> str:
    cell = row.select_one(selector)
    if cell is None:
        raise CrawlerError(f"Missing cell {selector!r}")
    return cell.get_text(strip=True)


def _has_best_picture_flag(row: Tag) -> bool:
    cell = row.select_one("td.film-best-picture")
    if cell is None:
        raise CrawlerError("Missing cell 'td.film-best-picture'")
    return cell.select_one("i") is not None
