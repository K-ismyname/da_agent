# Business Context

> Service and product context that AI agents must understand before analysis.
> Update this file when business model, target users, or product changes.

---

## Service Overview
- **Service**: The Formula — AI·데이터 실무자 커뮤니티 플랫폼
- **Target Users**: AI/데이터 직군 실무자, 취업 준비생
- **Business Model**: 커뮤니티 멤버십 (무료 소셜 가입)
- **Key Conversion**: 커뮤니티 가입 완료 — e-commerce 구매 아님

## Site Structure (실제 페이지)
- `/`            : 메인 피드 (아티클 목록, `?sort=popular|saved` 정렬, 상단 "인기 글 TOP5" 위젯)
- `/article/*`   : 아티클 상세 (핵심 콘텐츠 소비 지점, 해시태그·"관련 글 추천" 섹션 있음)
- `/archive`     : 아카이브(공식) 목록
- `/members`     : 직군별 멤버(포뮬러) — `?jobRole=` 필터
- `/activities`  : 모임
- `/apply`       : 가입 시작 (카카오/네이버 소셜 로그인 — **HTML `<form>` 태그 없음**)
- `/account`     : 로그인/가입 게이트 (NextAuth류, callbackUrl 리다이렉트)
- `/onboarding`  : 가입 직후 안내 페이지 (가입 완료 신호로 사용)

## North Star Metric
- **Primary**: 가입 전환율 (funnel_mart 기준, 방문 → 가입 완료)
- **Secondary**: 콘텐츠 소비율(page_view+scroll), 코호트 W1 리텐션

## 가입 퍼널 (funnel_mart, 순차형 5단계)
방문 → 콘텐츠 소비(page_view+scroll) → 가입 페이지 도달(`/apply`) →
로그인/가입 시도(`/account`) → 가입 완료(`/onboarding`)
- ⚠️ `form_start`/`form_submit`은 쓰지 않는다 — `/apply`가 소셜 로그인 버튼뿐
  `<form>` 태그가 없어 GA4 폼 이벤트가 발생하지 않기 때문. page_view 경로 기반.
- `/account`·`/onboarding`의 의미는 실측 트래픽 기반 추정치(서비스 담당 확인 필요).

## 지표 → Mart 매핑 (질문을 어느 마트로 보낼지 — 모호성 방지)
| 질문 주제 | 봐야 할 mart |
|---|---|
| 일자별 방문·세션·PV·참여율·재방문 | dashboard_kpi |
| **이탈률·전환·퍼널 단계** | **funnel_mart** (실험 마트의 bounce_rate와 혼동 금지) |
| 주차별 리텐션·코호트 | cohort_mart |
| 유입 채널 | marketing_channel_mart (단, 아래 신뢰도 경고 참조) |
| 페이지별 성과·인기 페이지 | landing_page_mart |
| 사용자 이동 경로 | journey_mart |
| 관련 글 추천 클릭률 | recommendation_mart |
| A/B 실험 (가입 배너/홈 정렬) | signup_prompt / home_sort 실험 마트 (Data Scientist A/B 분기) |

## 진행 중 A/B 실험 (목업 데이터 — 실기능 배포 후 실데이터로 교체)
- `signup_prompt`: 가입 유도 배너 수동 노출(A) vs 스크롤 90% 능동 노출(B)
- `home_sort`: 홈 기본 정렬 최신순(A) vs 인기순(B)
- ⚠️ `ab_test_mart`는 이 커뮤니티와 무관한 Meta Ads 스터디 예제 — 분석에 쓰지 말 것.

## What NOT to Assume
- e-commerce 구매 행동 가정 금지 (purchases/spend는 무관한 데모 마트 전용)
- 채널별 결론 도출 금지: UTM 미설정으로 모든 트래픽이 Direct 집계 → 신뢰도 LOW
- funnel_mart 없이 이탈률·전환율 수치 생성 금지
- "이탈률"은 기본적으로 funnel_mart의 단계별 이탈을 뜻함 — 실험 마트의 bounce_rate와 혼동 금지

---
> Last updated: 2026-07-10
