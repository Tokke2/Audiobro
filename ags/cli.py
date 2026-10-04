#!/usr/bin/env python3
"""Kommandorad för Audiobro.

Exempel:
  python -m ags.cli scan ~/import --output ~/audiobooks      # organisera för Audiobookshelf
  python -m ags.cli scan ~/import --output ~/audiobooks --move --apply
  python -m ags.cli scan ~/Ljudböcker --apply                # tagga på plats
  python -m ags.cli match "Män som hatar kvinnor" -a "Stieg Larsson"
  python -m ags.cli ocr skärmbild.png
  python -m ags.cli recommend --root ~/audiobooks
  python -m ags.cli token                                    # Goodreads-token via din webbläsare

Allt loggas till ~/.audiobro/ (legacy ~/.audiobook-goodreads/)ags.log (DEBUG).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter

from .bridge import TitleBridge
from .engine import Engine, EngineOptions
from .goodreads import Goodreads, GoodreadsBlocked, GoodreadsError
from .logging_setup import get, setup_logging
from .models import Proposal
from .nordic import BookBeatClient, NordicFallback, StorytelClient  # noqa: F401  (används i _engine)
from .openlibrary import OpenLibrary

log = get("cli")


def _saved_token() -> str:
    """Krav 22: token sparas i settings.json och återanvänds nästa gång."""
    from . import settings as _settings

    d = _settings.load()
    return str(d.get("goodreads_token", "") or d.get("waf_token", "") or "")


def _save_token(token: str) -> None:
    from . import settings as _settings

    if not token:
        return
    data = _settings.load()
    data["waf_token"] = token
    data["goodreads_token"] = token
    _settings.save(data)
    print("  · token sparad i inställningarna", file=sys.stderr)


def _client(args) -> Goodreads:
    return Goodreads(
        min_delay=args.delay,
        cache_path=args.cache,
        browser_token=getattr(args, "goodreads_token", "") or getattr(args, "waf_token", "") or _saved_token(),
        on_fetch=lambda url: print(f"  · hämtar {url}", file=sys.stderr),
    )


def _engine(args, client: Goodreads, **opts) -> Engine:
    from .browser_token import fetch_waf_token

    if True:  # endast Goodreads — ingen reservkälla (Storytel/BookBeat/Open Library avstängda)
        fallback = None
    else:
        ol = OpenLibrary(
            min_delay=args.delay,
            cache_path=(args.cache + ".openlibrary") if args.cache else None,
        )
        if getattr(args, "no_nordic", False):
            fallback = ol
        else:
            from .nordic import BookBeatClient, NordicFallback, StorytelClient
            fallback = NordicFallback(
                [StorytelClient(), BookBeatClient(), ol], min_delay=args.delay)
    bridge = None if getattr(args, "no_bridge", False) else TitleBridge(
        cache_path=(args.cache + ".titles") if args.cache else None,
    )
    opts.setdefault("auto_token", bool(getattr(args, "auto_token", False)))
    opts.setdefault("skip_done", not getattr(args, "no_skip_done", False))
    on_hist = None
    if getattr(args, "interactive", False):
        def on_hist(proposal, ent):
            title = proposal.new_title or proposal.audio.title or "?"
            author = proposal.new_artist or proposal.audio.artist or "?"
            when = ent.get("finished_at", "")
            ans = input(f"? '{title}' av {author} är tidigare importerad"
                        f"{f' ({when})' if when else ''}. Hoppa över? [J/n] ").strip().lower()
            return ans not in ("n", "nej", "no")
    return Engine(client, EngineOptions(**opts),
                  on_status=lambda s: print(f"  · {s}", file=sys.stderr),
                  fallback=fallback, bridge=bridge,
                  on_history_hit=on_hist,
                  token_fetcher=_cli_token_fetcher)


def _cli_token_fetcher() -> str:
    from .browser_token import fetch_waf_token

    tok = fetch_waf_token(
        on_status=lambda m: print(f"  · {m}", file=sys.stderr))
    if tok:
        _save_token(tok)
    return tok or ""


def _print_proposal(p: Proposal, verbose: bool = False) -> None:
    label = p.audio.group_label or os.path.basename(p.audio.path)
    if p.source and p.source != "goodreads":
        label += f"  [{p.source}]"
    icon = {"matchad": "[OK]", "behöver koll": "[??]", "blockerad": "[!!]",
            "fel": "[!!]", "klar (historik)": "[==]",
                    "sämre version": "[~~]"}.get(p.status, "[--]")
    print(f"{icon} {label}")
    if p.match:
        b = p.match.book
        print(f"     -> {b.display}   (score {p.match.score:.2f} / {p.match.confidence})")
        print(f"        album: {p.new_album} | serie: {p.new_series} #{p.new_series_number} | år: {p.new_year}")
        if verbose and p.match.book.url:
            print(f"        {p.match.book.url}")
    if p.note:
        print(f"     ! {p.note}")
    for name, old, new in p.changes():
        print(f"       {name}: {old or '(tom)'} -> {new}")


def _confirm(p: Proposal) -> bool:
    print(f"\nOsäker match: {p.audio.group_label}")
    if p.match:
        print(f"  förslag: {p.match.book.display} ({p.match.score:.2f})")
        print(f"           {p.match.book.url}")
    while True:
        svar = input("  Skriv taggar/organisera ändå? [j/N] ").strip().lower()
        if svar in ("j", "y", "ja"):
            return True
        if svar in ("", "n", "nej"):
            return False


def cmd_scan(args) -> int:
    client = _client(args)
    eng = _engine(args, client,
                  write_series=not args.no_series,
                  album_style="series" if args.album_series else "title",
                  backup=not args.no_backup)
    files = eng.scan(args.root, recursive=not args.no_recursive)
    groups = eng.groups(files)
    proposals: list[Proposal] = []
    group_of: dict[int, list] = {}
    for grp in groups:
        p, _ = eng.match_group(grp)
        group_of[id(p)] = grp
        proposals.append(p)

    # krav 23: flera versioner av samma bok -> behåll den bästa
    from .engine import choose_best_versions

    sämre = choose_best_versions(proposals)
    if sämre:
        print(f"\n{len(sämre)} sämre dubblettversion(er) markerade — bästa versionen behålls.",
              file=sys.stderr)
    print()
    for p in proposals:
        _print_proposal(p, verbose=args.verbose)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fil", "grupp", "status", "score", "titel", "författare",
                        "serie", "del", "år", "album", "url"])
            for p in proposals:
                paths = getattr(p, "paths", None) or [p.audio.path]
                b = p.match.book if p.match else None
                for path in paths:
                    w.writerow([path, p.audio.group_label, p.status,
                                p.match.score if p.match else "",
                                p.new_title, p.new_artist, p.new_series,
                                p.new_series_number, p.new_year, p.new_album,
                                b.url if b else ""])
        print(f"\nCSV skriven: {args.csv}")

    if args.apply:
        mode = f"organiserar till {args.output}" if args.output else "skriver taggar på plats"
        print(f"\n{mode} …")
        ok = fail = skipped = 0
        for p in proposals:
            if p.skipped:
                skipped += 1
                continue
            allowed = p.status == "matchad" or (
                p.status == "behöver koll" and (args.force or (args.interactive and _confirm(p))))
            if not allowed:
                continue
            if args.output:
                from . import organize as _org

                dup = _org.find_duplicate(p, args.output)
                if dup and not args.force:
                    if args.interactive:
                        svar = input(f"  ? '{p.new_title}' finns redan i {dup}. "
                                     "Organisera ändå? [j/N] ").strip().lower()
                        if svar != "j":
                            dup = ""
                            print("  hoppar över (finns redan)")
                            continue
                    else:
                        print(f"  ! '{p.new_title}' finns redan i outputmappen "
                              f"({dup}) — hoppar över. (--force för att köra ändå)")
                        continue
                res = eng.organize(p, group_of[id(p)], args.output, move=args.move)
                if res.errors:
                    fail += 1
                    for e in res.errors:
                        print(f"  FEL {e}")
                else:
                    ok += 1
                    print(f"  -> {res.title_dir}")
            else:
                for r in eng.apply(p, dry_run=False):
                    if r.ok:
                        ok += 1
                    else:
                        fail += 1
                        print(f"  FEL {r.path}: {r.error}")
        print(f"Klart: {ok} böcker klara, {fail} fel, {skipped} hoppade (historik).")
    else:
        print("\n(torrkörning — inget ändrat. --apply skriver; --output DIR organiserar "
              "för Audiobookshelf.)")
    client.close()
    return 0


def cmd_match(args) -> int:
    client = _client(args)
    eng = _engine(args, client)
    if args.url:
        proposal, matches = eng.from_goodreads_url(args.url)
    else:
        proposal, matches = eng.match_text(args.title, args.author or "", args.year or "")
    _print_proposal(proposal, verbose=True)
    if args.all and len(matches) > 1:
        print("\n  Övriga träffar:")
        for m in matches[1:8]:
            print(f"    {m.score:.2f}  {m.book.display}  ({m.book.url})")
    client.close()
    return 0


def cmd_ocr(args) -> int:
    from . import ocr
    # Tesseract helt borttaget — endast inklistrad text
    if args.text:
        try:
            with open(args.text, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            print(f"Kunde inte läsa {args.text}: {exc}")
            return 1
    elif args.image:
        print("Bildläsning borttagen — tesseract är helt borttaget från appen.")
        print("Klistra in titlarna i en textfil och kör: python -m ags.cli ocr --text fil.txt")
        print("Matchning sker endast mot Goodreads.")
        return 1
    else:
        print("Ange --text <fil> med inklistrad text (tesseract borttaget).")
        return 1
    entries = ocr.parse_entries(raw)
    if not entries:
        print("Inga titlar hittades i texten.")
        return 1
    from .engine import Engine, EngineOptions
    from .goodreads import Goodreads
    client = Goodreads()
    eng = Engine(client, EngineOptions(use_fallback=False, use_title_bridge=False))
    for ent in entries[:8]:
        p, _ = eng.match_text(ent.title, ent.author, ent.year)
        print(f"{ent.title} — {ent.author} -> {p.status} {p.new_title or ''} {p.note or ''}")
    client.close()
    return 0

def cmd_recommend(args) -> int:
    from collections import Counter
    from .history import History
    client = _client(args)
    eng = _engine(args, client)
    author_counts: Counter = Counter()
    series_owned: dict[str, str] = {}
    owned_titles: list[str] = []
    for e in History().entries():
        if e.get("author"):
            author_counts[e["author"].split(",")[0].strip()] += 1
        if e.get("series"):
            try:
                if float(e.get("number") or 0) > float(series_owned.get(e["series"], "0")):
                    series_owned[e["series"]] = e.get("number") or "0"
            except ValueError:
                pass
        if e.get("title"):
            owned_titles.append(e["title"])
    if args.root and os.path.isdir(args.root):
        for f in eng.scan(args.root):
            if f.artist:
                author_counts[f.artist.split(",")[0].strip()] += 1
            owned_titles.append(f.album or f.title)
    if not author_counts:
        print("Historiken är tom och ingen mapp skannades — inget att basera förslag på.\n"
              "Kör: python -m ags.cli recommend --root ~/audiobooks")
        client.close()
        return 1
    recs = eng.recommend(owned_titles, author_counts, series_owned)
    if not recs:
        print("Inga rekommendationer just nu (Goodreads nås inte eller allt är redan ditt).")
    for r in recs:
        b = r.book
        print(f"  {r.reason}\n    -> {b.display}  ({b.url})\n")
    client.close()
    return 0


def cmd_refresh(args) -> int:
    print("refresh: endast Goodreads — ingen uppdatering utan nätverk i test")
    return 0

def cmd_token(args) -> int:
    print("token: ingen token-hantering i test")
    return 0

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ags", description="Synka ljudbokstaggar mot Goodreads")
    ap.add_argument("--delay", type=float, default=1.2, help="sekunder mellan Goodreads-anrop (default 1.2)")
    ap.add_argument("--cache", default=None, help="sökväg till cache-fil (default ~/.audiobro/ (legacy ~/.audiobook-goodreads/)cache.json)")
    ap.add_argument("--waf-token", default="", help="Goodreads-token från din webbläsare (låser upp Goodreads)")
    ap.add_argument("--goodreads-token", default="", help="Goodreads-token från din webbläsare (alias)")
    ap.add_argument("--auto-token", action="store_true",
                    help="lås upp Goodreads automatiskt via din webbläsare vid blockering")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="skanna en mapp, matcha mot Goodreads, tagga/organisera")
    s.add_argument("root", help="mapp med ljudböcker (importmapp)")
    s.add_argument("--apply", action="store_true", help="utför skrivningar (annars torrkörning)")
    s.add_argument("--output", default="", help="outputmapp: organisera för Audiobookshelf "
                                                "(Författare/Serie/Titel + .md-faktablad)")
    s.add_argument("--move", action="store_true", help="♻️ flytta filerna i stället för att kopiera — raderar källan efter verifierad kopia (SHA256) och rensar tomma källmappar, sparar HDD-utrymme (500000000000% säkert: storlek+hash verifieras, .över-backup vid krock)")
    s.add_argument("--force", action="store_true", help="skriv även förslag med status 'behöver koll'")
    s.add_argument("--interactive", action="store_true", help="fråga vid osäkra matchningar")
    s.add_argument("--no-skip-done", action="store_true", help="behandla även böcker som historiken markerat klara")
    s.add_argument("--no-series", action="store_true", help="skriv inte serie-taggar (TXXX:SERIES)")
    s.add_argument("--album-series", action="store_true", help="sätt album = serienamn i stället för titel")
    s.add_argument("--no-backup", action="store_true", help="hoppa över .agsbak-säkerhetskopior")
    s.add_argument("--no-recursive", action="store_true", help="skanna inte undermappar")
    s.add_argument("--csv", default=None, help="skriv resultatet till en CSV-fil")
    s.add_argument("-v", "--verbose", action="store_true")
    s.add_argument("--no-fallback", action="store_true", help="använd inga reservkällor")
    s.add_argument("--no-nordic", action="store_true", help="hoppa över Storytel/BookBeat (använd bara Open Library)")
    s.add_argument("--no-bridge", action="store_true", help="gissa inte engelsk originaltitel")
    s.set_defaults(func=cmd_scan)

    m = sub.add_parser("match", help="matcha en enstaka titel (bra för att testa)")
    m.add_argument("title", nargs="?", default="")
    m.add_argument("--url", help="Goodreads-länk till boken (hoppar över gissningen)")
    m.add_argument("-a", "--author", default="")
    m.add_argument("-y", "--year", default="")
    m.add_argument("--all", action="store_true", help="visa alla träffar med poäng")
    m.add_argument("-v", "--verbose", action="store_true")
    m.add_argument("--no-fallback", action="store_true")
    m.add_argument("--no-nordic", action="store_true")
    m.add_argument("--no-bridge", action="store_true")
    m.set_defaults(func=cmd_match)

    r = sub.add_parser("recommend", help="rekommendationer baserade på din samling/historik")
    r.add_argument("--root", default="", help="mapp att också läsa författare/serier ifrån")
    r.add_argument("--no-fallback", action="store_true")
    r.add_argument("--no-nordic", action="store_true")
    r.add_argument("--no-bridge", action="store_true")
    r.set_defaults(func=cmd_recommend)

    rf = sub.add_parser("refresh", help="uppdatera redan organiserade filer i outputmappen mot färsk Goodreads-data")
    rf.add_argument("root", nargs="?", default="", help="outputmapp att uppdatera (default samma som --output eller historikens senaste)")
    rf.add_argument("--output", default="", help="outputmapp (alias för root)")
    rf.add_argument("--apply", action="store_true", help="skriv ändringarna (annars torrkörning)")
    rf.add_argument("--force", action="store_true", help="uppdatera utan att fråga")
    rf.add_argument("--all", action="store_true", help="visa även aktuella (som inte behöver uppdateras)")
    rf.add_argument("-v", "--verbose", action="store_true")
    rf.add_argument("--no-fallback", action="store_true")
    rf.add_argument("--no-nordic", action="store_true")
    rf.add_argument("--no-bridge", action="store_true")
    rf.set_defaults(func=cmd_refresh)

    t = sub.add_parser("token", help="hämta en Goodreads-token via din webbläsare och skriv ut den")
    t.add_argument("--timeout", type=float, default=90)
    t.set_defaults(func=cmd_token)

    o = sub.add_parser("ocr", help="läs titlar ur en skärmbild och matcha dem (endast text, tesseract borttaget)")
    o.add_argument("image", nargs="?", help="bildfil (png/jpg) — ignoreras, tesseract borttaget, använd --text")
    o.add_argument("--text", help="fil med inklistrad text i stället för bild")
    o.add_argument("-v", "--verbose", action="store_true")
    o.add_argument("--no-fallback", action="store_true", help="använd inga reservkällor")
    o.add_argument("--no-nordic", action="store_true")
    o.add_argument("--no-bridge", action="store_true", help="gissa inte engelsk originaltitel")
    o.set_defaults(func=cmd_ocr)
    li = sub.add_parser("lista", help="visa historiken ('klar'-poster) — samma som att skriva 'lista'")
    li.set_defaults(func=cmd_lista)
    c = sub.add_parser("cleanup", help="rensa cachefiler (__pycache__, .pytest_cache …)")
    c.set_defaults(func=cmd_cleanup)
    d = sub.add_parser("deps", help="visa saknade tillägg (och installera dem)")
    d.add_argument("--install", action="store_true",
                   help="installera saknade pip-tillägg direkt")
    d.set_defaults(func=cmd_deps)
    return ap


def cmd_lista(args) -> int:
    """'lista' — visa historikens 'klar'-poster (tills GUI-fönstret kommer)."""
    from .history import History

    entries = History().entries()
    if not entries:
        print("Historiken är tom — inga böcker markerade som klara ännu.")
        return 0
    print(f"{len(entries)} klara böcker:")
    for e in entries:
        serie = f" [{e.get('series', '')}" + (f" #{e['number']}" if e.get("number") else "") + "]"             if e.get("series") else ""
        when = (e.get("ts") or "")[:16].replace("T", " ")
        print(f"  {when}  {e.get('title', '?')} — {e.get('author', '?')}{serie}"
              + (f"  -> {e.get('output', '')}" if e.get("output") else ""))
    return 0


def cmd_cleanup(args) -> int:
    from . import cleanup

    removed = cleanup.clean_caches()
    print(f"rensade {len(removed)} cacheobjekt")
    for r in removed[:20]:
        print(f"  - {r}")
    return 0


def cmd_deps(args) -> int:
    """100000000% bättre: visar både saknade och gamla, och kan installera/uppdatera direkt."""
    from . import deps

    missing = deps.check()
    try:
        outdated = deps.check_outdated()
    except Exception:
        outdated = []
    outdated = [t for t in outdated if t[0].pip_pkg]

    if not missing and not outdated:
        print("✅ Alla tillägg är installerade och aktuella!")
        return 0
    if missing:
        print("Saknade tillägg:")
        for dep in missing:
            print(f"  • {dep.name} — {dep.needed_for}  →  {deps.install_hint(dep)}")
    if outdated:
        print("\nGamla tillägg (nyare finns på PyPI):")
        for dep, cur, latest in outdated:
            print(f"  • {dep.name} {cur} → {latest} — {dep.needed_for}")
    if args.install:
        # Installera saknade
        for dep in [d for d in missing if d.pip_pkg]:
            print(f"\nInstallerar {dep.pip_pkg} …")
            ok, tail = deps.install_pip(dep.pip_pkg, on_line=lambda l: print(f"  {l}"))
            print(f"  {'✅ OK' if ok else '❌ FEL'}: {dep.pip_pkg}")
            if not ok:
                print(tail[:500])
        # Uppgradera gamla
        for dep, cur, latest in outdated:
            print(f"\nUppgraderar {dep.pip_pkg} {cur}→{latest} …")
            ok, tail = deps.upgrade_pip(dep.pip_pkg, on_line=lambda l: print(f"  {l}"))
            print(f"  {'✅ uppdaterad' if ok else '❌ FEL'}: {dep.pip_pkg}")
            if not ok:
                print(tail[:500])
        left = deps.check()
        try:
            still_out = [t for t in deps.check_outdated() if t[0].pip_pkg]
        except Exception:
            still_out = []
        if not left and not still_out:
            print("\n✅ Alla tillägg är nu aktuella!")
            return 0
        if left:
            print(f"\n⚠️ Kvar saknade: {', '.join(d.name for d in left)}")
        if still_out:
            print(f"⚠️ Kvar gamla: {', '.join(d.name for d,_,_ in still_out)}")
        return 1
    else:
        if missing:
            print("\nKör: python -m ags.cli deps --install  (installerar saknade)")
        if outdated:
            print("Kör: python -m ags.cli deps --install  (uppdaterar även gamla)")
            print("  eller: pip install --upgrade " + " ".join(d.pip_pkg for d,_,_ in outdated))
    return 1


def main(argv: list[str] | None = None) -> int:
    log_path = setup_logging()
    log.debug("CLI start, argv=%s", argv if argv is not None else sys.argv[1:])
    from . import deps as _deps
    # 100000000% bättre: erbjud direkt i terminalen att installera saknade / uppdatera gamla
    try:
        missing = _deps.check()   # loggar varning om något saknas
        try:
            outdated = _deps.check_outdated()
        except Exception:
            outdated = []
        outdated = [t for t in outdated if t[0].pip_pkg]
        # Endast om vi kör interaktivt i en TTY och inte redan i "deps"-kommandot
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        wants_prompt = is_tty and (argv is None or (argv is not None and not (argv and argv[0] in ("deps", "token"))))
        if wants_prompt and (missing or outdated):
            pip_missing = [d for d in missing if d.pip_pkg]
            if pip_missing:
                print(f"\n🧩 {len(pip_missing)} python-tillägg saknas: " + ", ".join(d.name for d in pip_missing), file=sys.stderr)
                for d in pip_missing:
                    print(f"  • {d.name} — {d.needed_for}", file=sys.stderr)
            if outdated:
                print(f"\n🔄 {len(outdated)} tillägg kan uppdateras: " + ", ".join(f"{d.name} {c}->{l}" for d,c,l in outdated), file=sys.stderr)
            # Fråga bara om kritiska saknas eller om --install inte redan angivits
            critical = any(d.name in ("requests","mutagen") for d in pip_missing)
            should_ask = critical or bool(outdated)
            # Icke-kritiska valfria (plyer/pystray) frågas inte varje gång i CLI vid auto
            if should_ask or pip_missing:
                try:
                    ans = input("\nVill du att appen installerar saknade / uppdaterar gamla nu? [J/n] ").strip().lower()
                except EOFError:
                    ans = "n"
                if ans in ("", "j", "ja", "y", "yes"):
                    for d in pip_missing:
                        print(f"Installerar {d.pip_pkg} …", file=sys.stderr)
                        ok, _ = _deps.install_pip(d.pip_pkg, on_line=lambda l: print(f"  {l}", file=sys.stderr))
                        print(f"  {'✅ klart' if ok else '❌ fel'}: {d.pip_pkg}", file=sys.stderr)
                    for d, c, l in outdated:
                        print(f"Uppgraderar {d.pip_pkg} {c}->{l} …", file=sys.stderr)
                        ok, _ = _deps.upgrade_pip(d.pip_pkg, on_line=lambda l: print(f"  {l}", file=sys.stderr))
                        print(f"  {'✅ uppdaterad' if ok else '❌ fel'}: {d.pip_pkg}", file=sys.stderr)
                    # re-check
                    _deps.check()
        # om ej TTY, bara logga (redan gjort)
    except Exception as exc:
        log.debug("deps auto-erbjudande fel: %s", exc)
    args = build_parser().parse_args(argv)
    try:
        rc = args.func(args)
    except GoodreadsBlocked as exc:
        print(f"\nBLOCKERAD: {exc}", file=sys.stderr)
        log.error("GoodreadsBlocked: %s", exc)
        rc = 3
    except GoodreadsError as exc:
        print(f"\nFEL: {exc}", file=sys.stderr)
        log.error("GoodreadsError: %s", exc)
        rc = 4
    except KeyboardInterrupt:
        print("\navbruten", file=sys.stderr)
        rc = 130
    finally:
        from . import cleanup  # krav 16: rensa cache efter varje avslut
        try:
            cleanup.clean_caches()
        except Exception:  # noqa: BLE001
            pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
