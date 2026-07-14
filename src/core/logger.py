import sys
from loguru import logger


def setup_logger():
    # 기본 핸들러 제거 (중복 방지)
    logger.remove()

    # 콘솔 출력용
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG",
        colorize=True,
    )

    # 파일 저장용
    logger.add(
        "logs/domeok_server.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="INFO",
        rotation="10 MB",  # 파일이 10MB가 되면 새로 만듦
        retention="7 days",  # 7일이 지난 로그는 삭제
        compression="zip",  # 압축해서 보관 (용량 절약)
        encoding="utf-8",
    )
