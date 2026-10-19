"""Desktop entry point; no mouse/keyboard automation is performed."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Pokerist: visual poker math trainer")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--learn', action='store_true', help='Lessons, glossary and recognition report; no table setup needed')
    mode.add_argument('--record', action='store_true', help='Collect game-window screenshots with F8')
    mode.add_argument('--label', action='store_true', help='Offline screenshot album and card labelling editor')
    mode.add_argument('--calibrate', action='store_true')
    mode.add_argument('--collect', action='store_true')
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--profile', action='store_true', help='Bind the bundled Pokerist 3D screenshot preset to the game viewport')
    mode.add_argument('--check', action='store_true', help='Capture one frame and inspect recognition')
    parser.add_argument('--demo', action='store_true', help='No screen capture required')
    parser.add_argument('--config', type=Path, default=Path('config.json'))
    parser.add_argument('--album', type=Path, default=Path('captures/inbox'))
    parser.add_argument('--templates', type=Path, default=Path('templates'))
    parser.add_argument('--iterations', type=int, default=3000)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--delay', type=int, default=0, help='Seconds to switch to the game before capture (0-30)')
    parser.add_argument('--window-title', default='', help='Target Windows title for calibration, recording or live HUD (Texas Poker by default in the launcher)')
    args = parser.parse_args()
    if not 0 <= args.delay <= 30:
        parser.error('--delay must be 0-30 seconds')
    if args.window_title and not (args.calibrate or args.record or args.run):
        parser.error('--window-title is only used with --calibrate, --record or --run')
    if args.iterations < 2000:
        parser.error('--iterations must be >= 2000')
    if args.delay:
        import time
        for seconds in range(args.delay, 0, -1):
            print(f'Switch to the game: capture in {seconds}s', flush=True)
            time.sleep(1)
    if args.learn:
        from learn_window import LearnWindow
        LearnWindow().run()
    elif args.record:
        from batch_capture import BatchCapture
        BatchCapture(args).run()
    elif args.label:
        from album_editor import AlbumEditor
        AlbumEditor(args).run()
    elif args.calibrate or args.collect or args.profile:
        from calibrator import CalibrationApp
        from profile_support import BUILTIN
        CalibrationApp(args.config, args.templates, collect=args.collect, window_title=args.window_title, profile_path=BUILTIN if args.profile else None).run()
    elif args.check:
        from check_screen import check
        check(args.config, args.templates)
    else:
        from hud_overlay import HUD
        HUD(args).run()


if __name__ == '__main__':
    main()
