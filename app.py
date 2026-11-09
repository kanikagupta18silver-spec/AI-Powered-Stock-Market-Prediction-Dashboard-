"""Compatibility launcher for the Streamlit dashboard."""

from pathlib import Path

from streamlit.web import cli

if __name__ == "__main__":
    dashboard = Path(__file__).with_name("streamlit_app.py")
    cli.main(args=["run", str(dashboard)], prog_name="streamlit", standalone_mode=False)
