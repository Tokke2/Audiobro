#!/usr/bin/env python3
"""Kommandorad för audiobook-goodreads-sync.

Exempel:
  python -m ags.cli scan ~/import --output ~/audiobooks      # organisera för Audiobookshelf
  python -m ags.cli scan ~/import --output ~/audiobooks --move --apply
  python -m ags.cli scan ~/Ljudböcker --apply                # tagga på plats
  python -m ags.cli match "Män som hatar kvinnor" -a "Stieg Larsson"
  python -m ags.cli ocr skärmbild.png
  python -m ags.cli recommend --root ~/audiobooks
  python -m ags.cli token                                    # WAF-token via din webbläsare

Allt loggas till ~/.audiobook-goodreads/ags.log (DEBUG).
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

    return str(_settings.load().get("waf_token", "") or "")


def _save_token(token: str) -> None:
    from . import settings as _settings

    if not token:
        return
    data = _settings.load()
    data["waf_token"] = token
    _settings.save(data)
    print("  · token sparad i inställningarna", file=sys.stderr)


def _client(args) -> Goodreads:
    return Goodreads(
        min_delay=args.delay,
        cache_path=args.cache,
        browser_token=getattr(args, "waf_token", "") or _saved_token(),
        on_fetch=lambda url: print(f"  · hämtar {url}", file=sys.stderr),
    )


def _engine(args, client: Goodreads, **opts) -> Engine:
    from .browser_token import fetch_waf_token

    if getattr(args, "no_fallback", False):
        fallback = None
    else:
        ol = OpenLibrary(
            min_delay=args.delay,
            cache_path=(args.cache + ".openlibrary") if args.cache else None,
        )
        if getattr(args, "no_nordic", False):
            fallback = ol
        else:
            # svenska titlar: Storytel/BookBeat först (har seriedata), sedan OL
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

    if args.text:
        with open(args.text, encoding="utf-8") as fh:
            raw = fh.read()
    elif args.image:
        if not ocr.tesseract_available():
            print("tesseract saknas. Installera det (macOS: brew install tesseract tesseract-lang, "
                  "Ubuntu: sudo apt install tesseract-ocr tesseract-ocr-swe) eller kör:\n"
                  f"  python -m ags.cli ocr --text fil_med_text.txt", file=sys.stderr)
            return 2
        raw = ocr.ocr_image(args.image)
        print("--- OCR-text ---")
        print(raw)
        print("----------------")
    else:
        print("Ange --image bild.png eller --text text.txt", file=sys.stderr)
        return 2

    entries = ocr.parse_entries(raw)
    if not entries:
        print("Kunde inte läsa några titlar ur texten.")
        return 1
    client = _client(args)
    eng = _engine(args, client)
    print(f"{len(entries)} titlar tolkade — matchar …\n")
    for i, e in enumerate(entries):
        proposal, _ = eng.match_text(e.title, e.author, e.year)
        print(f"#{i + 1} från skärmbild: {e.title} / {e.author or 'okänd författare'}")
        _print_proposal(proposal, verbose=args.verbose)
        print()
    client.close()
    return 0


def cmd_refresh(args) -> int:
    """Uppdatera redan organiserade filer i outputmappen mot färsk Goodreads-data."""
    import os
    from .history import History
    client = _client(args)
    eng = _engine(args, client)
    out_root = args.output or args.root
    if not out_root or not os.path.isdir(out_root):
        print(f"FEL: outputmappen finns inte: {out_root}", file=sys.stderr)
        return 2
    print(f"Skannar outputmappen {out_root} efter böcker att uppdatera …")
    proposals = eng.check_output_for_updates(out_root)
    if not proposals:
        print("Inga böcker hittade i outputmappen.")
        client.close()
        return 0
    # filtrera till de som behöver uppdateras om inte --all
    to_update = [p for p in proposals if p.status == "behöver uppdateras"]
    print(f"{len(proposals)} böcker skannade, {len(to_update)} behöver uppdateras.")
    for prop in proposals:
        flag = "🔄" if prop.status == "behöver uppdateras" else "✅"
        print(f"  {flag} {prop.audio.path} — {prop.status}: {prop.note}")
        if args.verbose:
            for k, old, new in getattr(prop, "_diffs", [])[:5]:
                print(f"      {k}: '{old}' → '{new}'")
    if not to_update:
        print("Allt redan aktuellt — inget att uppdatera.")
        client.close()
        return 0
    if not args.apply:
        print("\n(torrkörning — inget ändrat. Lägg till --apply för att skriva.)")
        client.close()
        return 0
    # bekräfta om inte --force
    if not args.force:
        # i CLI kräver vi explicit --force eller --interactive
        # för enkelhet: om inte force, fråga interaktivt om möjligt
        try:
            svar = input(f"Uppdatera {len(to_update)} bok/böcker? [j/N] ").strip().lower()
            if svar != "j":
                print("Avbrutet.")
                client.close()
                return 0
        except EOFError:
            print("Lägg till --force för att uppdatera utan fråga.")
            client.close()
            return 1
    ok = fail = 0
    for prop in to_update:
        # hitta gruppen igen via scan
        group = [f for f in eng.scan(out_root, recursive=True) if os.path.dirname(f.path) == os.path.dirname(prop.paths[0])] if hasattr(prop, "paths") else []
        # fallback: använd proposal.paths
        if not group and hasattr(prop, "paths"):
            import ags.library as lib
            # återskapa AudioFiles från paths
            group = []
            for pp in prop.paths:
                af = lib.scan(pp, recursive=False)
                if af:
                    group.extend(af)
                else:
                    # pp är redan en fil
                    from ags.models import AudioFile
                    # försök läsa tags för att skapa dummy
                    group.append(AudioFile(path=pp))
            if not group:
                # använd direkt paths som grupp
                from ags.models import AudioFile
                group = [AudioFile(path=pp) for pp in prop.paths]
        try:
            res_list = eng.apply_update(prop, group)
            if any(not r.ok for r in res_list):
                fail += 1
                for r in res_list:
                    if not r.ok:
                        print(f"  FEL {r.path}: {r.error}")
            else:
                ok += 1
                print(f"  ✔ uppdaterad: {prop.new_title} — {prop.new_series} #{prop.new_series_number}")
        except Exception as exc:
            fail += 1
            print(f"  FEL {prop.audio.path}: {exc}")
    print(f"Klart: {ok} uppdaterade, {fail} fel.")
    client.close()
    return 0 if fail == 0 else 1


def cmd_token(args) -> int:
    from .browser_token import fetch_waf_token

    try:
        token = fetch_waf_token(timeout=args.timeout, on_status=lambda m: print(f"  · {m}", file=sys.stderr))
    except RuntimeError as exc:
        print(f"FEL: {exc}", file=sys.stderr)
        return 5
    print(token)
    _save_token(token)
    return 0


def cmd_recommend(args) -> int:
    from .history import History

    client = _client(args)
    eng = _engine(args, client)
    hist = History()
    author_counts: Counter = Counter()
    series_owned: dict[str, str] = {}
    owned_titles: list[str] = []
    for e in hist.entries():
        if e.get("author"):
            author_counts[e["author"].split(",")[0].strip()] += 1
        if e.get("series"):
            cur = series_owned.get(e["series"], "0")
            try:
                if float(e.get("number") or 0) > float(cur):
                    series_owned[e["series"]] = e.get("number") or cur
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


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ags", description="Synka ljudbokstaggar mot Goodreads")
    ap.add_argument("--delay", type=float, default=1.2, help="sekunder mellan Goodreads-anrop (default 1.2)")
    ap.add_argument("--cache", default=None, help="sökväg till cache-fil (default ~/.audiobook-goodreads/cache.json)")
    ap.add_argument("--waf-token", default="", help="aws-waf-token-cookie från din webbläsare (låser upp Goodreads)")
    ap.add_argument("--auto-token", action="store_true",
                    help="lås upp WAF automatiskt via din Brave/Chromium-webbläsare vid blockering")
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

    t = sub.add_parser("token", help="hämta en aws-waf-token via din webbläsare och skriv ut den")
    t.add_argument("--timeout", type=float, default=90)
    t.set_defaults(func=cmd_token)

    o = sub.add_parser("ocr", help="läs titlar ur en skärmbild och matcha dem")
    li = sub.add_parser("lista", help="visa historiken ('klar'-poster) — samma som att skriva 'lista'")
    li.set_defaults(func=cmd_lista)
    c = sub.add_parser("cleanup", help="rensa cachefiler (__pycache__, .pytest_cache …)")
    c.set_defaults(func=cmd_cleanup)
    d = sub.add_parser("deps", help="visa saknade tillägg (och installera dem)")
    d.add_argument("--install", action="store_true",
                   help="installera saknade pip-tillägg direkt")
    d.set_defaults(func=cmd_deps)
    o.add_argument("image", nargs="?", help="bildfil (png/jpg)")
    o.add_argument("--text", help="fil med inklistrad text i stället för bild")
    o.add_argument("-v", "--verbose", action="store_true")
    o.add_argument("--no-fallback", action="store_true", help="använd inga reservkällor")
    o.add_argument("--no-nordic", action="store_true")
    o.add_argument("--no-bridge", action="store_true", help="gissa inte engelsk originaltitel")
    o.set_defaults(func=cmd_ocr)
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
    from . import deps

    missing = deps.check()
    if not missing:
        print("Alla tillägg är installerade.")
        return 0
    for dep in missing:
        print(f"saknas: {dep.name} — {dep.needed_for}  ->  {deps.install_hint(dep)}")
    if args.install:
        for dep in [d for d in missing if d.pip_pkg]:
            ok, _ = deps.install_pip(dep.pip_pkg, on_line=lambda l: print(f"  {l}"))
            print(f"  {'OK' if ok else 'FEL'}: {dep.pip_pkg}")
        left = deps.check()
        return 0 if not left else 1
    return 1


def main(argv: list[str] | None = None) -> int:
    log_path = setup_logging()
    log.debug("CLI start, argv=%s", argv if argv is not None else sys.argv[1:])
    from . import deps as _deps
    _deps.check()   # loggar varning om något saknas
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
