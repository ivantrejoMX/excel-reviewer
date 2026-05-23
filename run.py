"""Convenience launcher: python run.py from the excel-reviewer directory."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
