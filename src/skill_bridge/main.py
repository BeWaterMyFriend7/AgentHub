import uvicorn
from skillbridge.config import HOST, PORT


def main():
    uvicorn.run("skillbridge.routes:app", host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
