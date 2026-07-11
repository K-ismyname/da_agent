# 분석 대상 서비스 — 프로젝트 개요

## 서비스
AX(AI × 실무) 실전 스터디 커뮤니티
- 핵심 가치: AI를 업무에 적용하는 공식을 아카이브하고 나누는 공간

## 핵심 기능
- 아티클: AI 큐레이터가 정제한 AX 콘텐츠 피드
- 아카이브: 직무별 업무 공식 저장소
- 포뮬러: 멤버 전용 공식 공유
- 모임: 오프라인/온라인 활동

## 핵심 전환 (Conversion)
방문 → 아티클 열람 → 가입하기 → 포뮬러 저장

## 기술 스택
- Frontend: Next.js (Vercel 배포)
- Analytics: GA4 (측정 ID: G-3T1X4Z1H28) ✅
- Data Warehouse: BigQuery (dataset: formula_silk_analytics) ✅
- AI Agent: OpenAI GPT-4o (tool calling)
- Agent Backend: Python FastAPI + LangGraph (Railway 상시 실행)

## 분석 목표
GA4 데이터를 AI 에이전트 팀이 자동 분석해서
"왜 이탈이 생기는지", "어떤 채널이 가입을 만드는지" 답하는 대시보드 구축

## 분석 대상 지표
- 가입 전환율 (방문 → 가입)
- 아티클별 체류 시간 / 스크롤률
- 채널별 유입 품질 (Organic vs Direct vs Social)
- 코호트 재방문율

## 현재 진행 상태
- [x] GA4 속성 생성 (G-3T1X4Z1H28)
- [x] Next.js에 GA4 코드 삽입 (PR 완료)
- [x] Mart 테이블 생성 (formula_silk_analytics 11개)
- [x] GA4 → BigQuery 내보내기 연결 (analytics_543337410.events_*)
- [x] AI 에이전트 파이프라인 구축 (7노드 LangGraph, Railway 배포)
- [x] 대시보드 완성 (Vercel 배포)
