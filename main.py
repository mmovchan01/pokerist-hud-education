"""Desktop entry point; no mouse/keyboard automation is performed."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Pokerist: visual poker math trainer")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--calibrate', action='store_true')
    mode.add_argument('--collect', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--demo', action='store_true', help='No screen capture required')
    parser.add_argument('--config', type=Path, default=Path('config.json'))
    parser.add_argument('--templates', type=Path, default=Path('templates'))
    parser.add_argument('--iterations', type=int, default=3000)
    parser.add_argument('--seed', type=int, default=None)
    args = parser.parse_args()
    if args.iterations < 2000:
        parser.error('--iterations must be >= 2000')
    if args.calibrate or args.collect:
        from calibrator import CalibrationApp
        CalibrationApp(args.config, args.templates, collect=args.collect).run()
    else:
        from hud_overlay import HUD
        HUD(args).run()


if __name__ == '__main__':
    main()
