"""Organisera ljudböcker för Audiobookshelf:

    <output>/<Författare>/<Serie>/<Titel>/<filer>

Mappar OCH filer namnges, flera discar slås ihop till löpande spårnummer
(disc 2 får 13–24 när disc 1 hade 1–12) och ett .md-faktablad med bokinfo
och ljudkvalitet skrivs bredvid filerna.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Optional

from . import audioinfo, tags
from .logging_setup import get
from .models import AudioFile, Proposal

log = get("organize")

BAD_CHARS = re.compile(r'[\\/:*?"<>|]')


def safe_name(s: str, max_len: int = 80) -> str:
    """Fil-/mappsäkert namn utan skumma tecken."""
    s = BAD_CHARS.sub("", s or "").replace("\t", " ")
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:max_len] or "namnlös"


def _track_num(f: AudioFile) -> tuple:
    m = re.search(r"(\d+)", f.track or "")
    if m:
        return (0, int(m.group(1)), f.path)
    m = re.search(r"(\d+)", os.path.splitext(os.path.basename(f.path))[0])
    if m:
        return (0, int(m.group(1)), f.path)
    return (1, 0, f.path)


def order_files(files: list[AudioFile]) -> list[AudioFile]:
    """Sortera inom en bok: disc först, sedan spår/filnamn (löpn. numrering)."""
    return sorted(files, key=lambda f: (f.disc or 0, _track_num(f)))


@dataclass
class Action:
    src: str = ""
    dst: str = ""
    kind: str = ""       # copy / move / md / tags
    note: str = ""


@dataclass
class OrganizeResult:
    title_dir: str = ""
    actions: list[Action] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    md_path: str = ""


def series_prefix(number: str) -> str:
    """Delnummer -> sorterbar mapp-prefix: '1'->'01', '12'->'12', '2.5'->'2.5'."""
    n = (number or "").strip()
    if not n:
        return ""
    try:
        v = float(n)
    except ValueError:
        return ""
    if v <= 0:
        return ""
    return f"{int(v):02d}" if v.is_integer() else f"{v:g}"
    cover_path: str = ""


def plan(proposal: Proposal, group: list[AudioFile], out_root: str) -> list[Action]:
    """Beräkna vart varje fil ska — utan att röra något."""
    author = safe_name((proposal.new_artist or "").split(",")[0] or "Okänd författare")
    title = safe_name(proposal.new_title or proposal.audio.album or "Okänd titel")
    series = safe_name(proposal.new_series) if (proposal.new_series or "").strip() else ""
    parts = [out_root, author]
    if series:
        parts.append(series)
        # serieböcker sorteras efter delnummer: "01 - Isprinsessan"
        pref = series_prefix(proposal.new_series_number)
        parts.append(f"{pref} - {title}" if pref else title)
    else:
        parts.append(title)
    title_dir = os.path.join(*parts)

    ordered = order_files(group)
    multi = len(ordered) > 1
    actions: list[Action] = []
    for i, f in enumerate(ordered, 1):
        ext = os.path.splitext(f.path)[1]
        name = f"{i:02d} - {title}{ext}" if multi else f"{title}{ext}"
        actions.append(Action(src=f.path, dst=os.path.join(title_dir, name), kind="file"))
    actions.append(Action(dst=os.path.join(title_dir, f"{title}.md"), kind="md"))
    return actions


def find_duplicate(proposal: Proposal, out_root: str) -> str:
    """Finns samma titel+författare redan i outputmappen? Returnera sökvägen
    (tom sträng annars). Skydd mot att organisera samma bok två gånger."""
    author = safe_name((proposal.new_artist or "").split(",")[0] or "")
    title = safe_name(proposal.new_title or proposal.audio.album or "")
    if not author or not title:
        return ""
    a_dir = os.path.join(out_root, author)
    if not os.path.isdir(a_dir):
        return ""
    pref_re = re.compile(r"^\d+(?:\.\d+)?\s*-\s*")

    def _hits(folder: str) -> str:
        for name in os.listdir(folder):
            full = os.path.join(folder, name)
            if not os.path.isdir(full):
                continue
            if pref_re.sub("", name) == title and os.listdir(full):
                return full
        return ""

    for sub in os.listdir(a_dir):              # serie-mappar (eller titlar rakt i)
        full = os.path.join(a_dir, sub)
        if not os.path.isdir(full):
            continue
        hit = _hits(full)                      # titlar under serien
        if hit:
            return hit
    return _hits(a_dir)                        # titlar direkt under författaren


def _file_hash(path: str, limit_mb: int = 200) -> str:
    """SHA256 för filen (begränsad för 500bn% verifiering)."""
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            size = os.path.getsize(path)
            if size <= limit_mb * 1024 * 1024:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            else:
                h.update(str(size).encode())
                h.update(fh.read(1024 * 1024))
                try:
                    fh.seek(-1024 * 1024, 2)
                    h.update(fh.read(1024 * 1024))
                except OSError:
                    pass
    except OSError:
        return ""
    return h.hexdigest()


def _try_remove_empty_parents(src_path: str) -> None:
    """Rensa tomma källmappar efter flytt (sparar HDD-utrymme, ingen dataförlust)."""
    try:
        cur = os.path.dirname(os.path.abspath(src_path))
        for _ in range(4):
            if not os.path.isdir(cur):
                break
            if os.listdir(cur):
                break
            try:
                os.rmdir(cur)
                log.info("rensade tom källmapp %s", cur)
            except OSError:
                break
            cur = os.path.dirname(cur)
    except Exception:
        pass


def _safe_move(src: str, dst: str) -> None:
    """500000000000% säker flytt: verifierad, atomär där det går, hash-kontrollerad vid kopiering över enheter."""
    dst_dir = os.path.dirname(dst)
    os.makedirs(dst_dir, exist_ok=True)
    src_size = os.path.getsize(src)
    src_hash = _file_hash(src) if src_size and src_size < 500 * 1024 * 1024 else ""
    backup = None
    if os.path.exists(dst):
        backup = dst + ".över"
        try:
            os.replace(dst, backup)
        except OSError as exc:
            raise OSError(f"kunde inte säkerhetskopiera befintlig fil: {exc}") from exc
    try:
        try:
            dst_dev = os.stat(dst_dir).st_dev
            src_dev = os.stat(src).st_dev
            same_fs = (dst_dev == src_dev)
        except OSError:
            same_fs = False
        if same_fs:
            os.replace(src, dst)
        else:
            shutil.copy2(src, dst)
            try:
                dst_size = os.path.getsize(dst)
            except OSError as exc:
                raise OSError(f"mål saknas efter kopiering: {exc}") from exc
            if dst_size != src_size:
                try:
                    os.remove(dst)
                except OSError:
                    pass
                raise OSError(f"storleksfel efter kopiering ({src_size} -> {dst_size})")
            if src_hash:
                dst_hash = _file_hash(dst)
                if dst_hash and dst_hash != src_hash:
                    try:
                        os.remove(dst)
                    except OSError:
                        pass
                    raise OSError("hash-fel efter kopiering — källan behålls")
            os.unlink(src)
        if not os.path.exists(dst):
            raise OSError("mål saknas efter flytt")
        try:
            if os.path.getsize(dst) != src_size:
                raise OSError("storleksfel efter flytt")
        except OSError:
            pass
        if backup and os.path.exists(backup):
            try:
                os.remove(backup)
                log.info("tog bort gammal backup %s", backup)
            except OSError:
                pass
        _try_remove_empty_parents(src)
    except Exception:
        if backup and os.path.exists(backup) and not os.path.exists(dst):
            try:
                os.replace(backup, dst)
            except OSError:
                pass
        raise


def execute(proposal: Proposal, group: list[AudioFile], out_root: str,
            move: bool = False, write_series: bool = True) -> OrganizeResult:
    """Kopiera/flytta filer, skriv taggar + .md på målet. Källor rörs aldrig vid copy."""
    res = OrganizeResult()
    actions = plan(proposal, group, out_root)
    res.title_dir = os.path.dirname(actions[-1].dst)
    file_actions = [a for a in actions if a.kind == "file"]
    try:
        os.makedirs(res.title_dir, exist_ok=True)
    except OSError as exc:
        res.errors.append(f"kunde inte skapa mapp: {exc}")
        return res

    if file_actions:
        try:
            total_bytes = sum(os.path.getsize(a.src) for a in file_actions if os.path.exists(a.src))
            free = shutil.disk_usage(res.title_dir).free
            if total_bytes and free < total_bytes + 50 * 1024 * 1024:
                res.errors.append(f"för lite ledigt utrymme i {out_root} ({free // (1024*1024)} MB ledigt, behöver ~{total_bytes // (1024*1024)} MB)")
                log.error("för lite utrymme: behöver %d, har %d", total_bytes, free)
                return res
        except OSError:
            pass

    fields = tags.proposal_to_fields(proposal, write_series=write_series)
    total = len(file_actions)

    for i, act in enumerate(file_actions, 1):
        if os.path.abspath(act.src) == os.path.abspath(act.dst):
            act.kind = "tags"
            res.actions.append(act)
            continue
        if not os.path.exists(act.src):
            # Självreparation: en avbruten/dubbel körning kan ha lämnat målet
            # omdöpt till ".över" — återställ det i stället för att krascha.
            heal = act.dst + ".över"
            if os.path.exists(heal) and not os.path.exists(act.dst):
                os.replace(heal, act.dst)
                log.warning("återställde %s från .över (tidigare körning "
                            "avbröts/dubbelkördes)", act.dst)
                act.kind = "tags"
                res.actions.append(act)
            else:
                res.errors.append(f"källfilen saknas (redan flyttad?): "
                                  f"{os.path.basename(act.src)}")
            continue
        try:
            if move:
                _safe_move(act.src, act.dst)
            else:
                shutil.copy2(act.src, act.dst)
        except OSError as exc:
            res.errors.append(f"{os.path.basename(act.src)}: {exc}")
            continue
        act.kind = "move" if move else "copy"
        res.actions.append(act)
        log.info("%s %s -> %s", act.kind, act.src, act.dst)
        f = {**fields}
        if total > 1:
            f["track"] = f"{i}/{total}"
        wr = tags.write_file(act.dst, f, backup=False)
        if not wr.ok:
            res.errors.append(f"taggar {os.path.basename(act.dst)}: {wr.error}")
        else:
            log.info("taggar skrivna: %s", sorted(wr.written))

    # .md-faktablad med bokinfo + ljudkvalitet (läst från målfilerna)
    md_action = next((a for a in actions if a.kind == "md"), None)
    if md_action and not res.errors:
        written = [a.dst for a in file_actions]
        qualities = [audioinfo.probe(p) for p in written]
        md = audioinfo.book_md(
            title=proposal.new_title or proposal.audio.album,
            author=proposal.new_artist,
            album=proposal.new_album,
            series=proposal.new_series,
            series_number=proposal.new_series_number,
            year=proposal.new_year,
            url=proposal.match.book.url if proposal.match else "",
            source=proposal.source or "",
            score=proposal.match.score if proposal.match else 0.0,
            qualities=qualities,
            extra_note=proposal.note,
            subtitle=proposal.new_subtitle,
            narrator=proposal.new_narrator,
            publisher=proposal.new_publisher,
            genre=proposal.new_genre,
            language=proposal.new_language,
            description=proposal.new_description,
        )
        try:
            with open(md_action.dst, "w", encoding="utf-8") as fh:
                fh.write(md)
            res.md_path = md_action.dst
            md_action.kind = "md"
            res.actions.append(md_action)
            log.info("skrev faktablad %s", md_action.dst)
        except OSError as exc:
            res.errors.append(f"md: {exc}")

    # cover.jpg i titelmappen — Audiobookshelf plockar upp den automatiskt
    cover_url = (proposal.match.book.cover if proposal.match else "") or getattr(
        proposal, "cover_url", "")
    if cover_url and not res.errors:
        try:
            import requests

            resp = requests.get(
                cover_url,
                headers={"User-Agent": "audiobook-goodreads-sync/1.0"},
                timeout=30)
            head = resp.content[:4]
            if resp.status_code == 200 and (
                    head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG")
                    or head.startswith(b"GIF8")):
                cov = os.path.join(res.title_dir, "cover.jpg")
                with open(cov, "wb") as fh:
                    fh.write(resp.content)
                res.cover_path = cov
                log.info("sparade omslag: %s (%d bytes)", cov, len(resp.content))
            else:
                log.warning("omslag hoppades över (%s -> HTTP %s)", cover_url, resp.status_code)
        except Exception as exc:  # omslag är nice-to-have, aldrig ett fel
            log.warning("kunde inte hämta omslag %s: %s", cover_url, exc)
    return res
