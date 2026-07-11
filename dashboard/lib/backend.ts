// FastAPI 백엔드 호출 공통 헬퍼 — 공유 시크릿 헤더 부착
//
// [역할]
// dashboard/app/api/*/route.ts (3개 프록시 라우트)가 전부 이 함수를 통해
// Python FastAPI 백엔드(agent_backend/main.py)를 호출한다. "백엔드 URL을
// 어디서 가져오고, 인증 헤더를 어떻게 붙일지"를 한 곳에 모아둔 얇은 래퍼.
//
// [왜 이렇게 설계했나]
// - main.py의 require_shared_secret 미들웨어가 x-backend-secret 헤더를
//   검사하는데, 이 헤더 부착 로직을 라우트마다 반복하면 하나라도 빠뜨릴
//   위험이 있다. 여기 한 곳에만 두면 새 API 라우트를 추가해도 이 함수만
//   쓰면 자동으로 인증이 붙는다.
// - fetch()를 그대로 감싼 이유: 프록시 라우트 입장에서는 "일반 fetch를
//   쓰는 것과 거의 동일한 사용감"을 유지하면서, path와 init(메서드/바디 등)만
//   넘기면 나머지(base URL, 인증 헤더)는 신경 안 써도 되게 하기 위함.
const BACKEND_URL = process.env.AGENT_BACKEND_URL ?? 'http://localhost:8000'  // 배포 환경에선 실제 백엔드 서버 주소, 로컬 개발 시 기본값으로 폴백

export function backendFetch(path: string, init?: RequestInit) {
  const secret = process.env.BACKEND_SHARED_SECRET
  return fetch(`${BACKEND_URL}${path}`, {
    ...init,                                              // 호출부가 넘긴 메서드/바디 등을 그대로 보존
    headers: {
      ...init?.headers,                                   // 호출부가 헤더를 넘겼다면 유지
      ...(secret ? { 'x-backend-secret': secret } : {}),  // 시크릿이 설정된 경우에만 부착 — 로컬 개발(미설정)에서는 그냥 생략됨(main.py도 동일 조건)
    },
  })
}
