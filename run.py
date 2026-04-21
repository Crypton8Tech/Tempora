"""Run TemporaShop web server."""

import sys
import uvicorn


def run_web():
    """Run FastAPI web server."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "seed":
            print("🌱 Seeding database...")
            from seed_data import seed
            seed()
        elif cmd == "web":
            print("🌐 Starting web server on http://0.0.0.0:8000")
            run_web()
        else:
            print("Usage: python run.py [web|seed]")
    else:
        print("🌐 Starting web server on http://0.0.0.0:8000")
        run_web()
