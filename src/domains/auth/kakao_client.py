import httpx

from core.exception.exceptions import BadRequestException, ExternalServiceException

KAKAO_USER_ME_URL = "https://kapi.kakao.com/v2/user/me"


async def fetch_kakao_user_id(access_token: str) -> str:
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(KAKAO_USER_ME_URL, headers=headers)
    except httpx.HTTPError as exc:
        raise ExternalServiceException(
            detail="카카오 인증 서버와 통신에 실패했습니다."
        ) from exc

    if response.status_code == 401:
        raise BadRequestException(detail="카카오 인증 실패")
    if response.status_code != httpx.codes.OK:
        raise ExternalServiceException(
            detail="카카오 사용자 정보를 가져오지 못했습니다."
        )

    data = response.json()
    kakao_id = data.get("id")
    if kakao_id is None:
        raise BadRequestException(detail="카카오 인증 실패")
    return str(kakao_id)
