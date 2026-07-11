# Meta Ads × GA4 A/B 테스트 & 퍼널 분석 — 스터디 노트 정리

> 원본: **JU DATA / 주정민(Joon), "Meta Ads GA4 Study Note"** (2026-06-29, 32p)
> 정리 목적: 노트 전체를 섹션별로 세밀하게 풀어서 재구성 — `da_agent` 프로젝트의 A/B Test 파트(`ab_test_mart`, `run_ab_significance_test`) 참고용

---

## 0. 한눈에 보는 전체 구조

이 노트의 핵심 아이디어는 딱 하나입니다.

> **Meta 광고 데이터와 GA4 랜딩 페이지 데이터를 `join_key`로 합쳐서, A/B 테스트(가로 비교)와 퍼널 분석(세로 비교)을 동시에 할 수 있게 만든다.**

```
Meta Ads (광고주 관점)          GA4 (사용자 관점)
 노출·클릭·비용·픽셀 구매          세션·장바구니·실제 구매·매출
        │                              │
        └────────── join_key ──────────┘   ← inner join
        date_campaignid_adid_abvariant
                     │
          Merged A/B dataset (9 rows × 79 cols)
                     │
        ┌────────────┴────────────┐
   A/B 통계 검정              퍼널 분석
 (A_Control vs B_Variant)   (click→session→cart→purchase)
```

- **가로 비교(A/B 테스트):** "A 버전과 B 버전 중 어느 것이 더 성과가 좋은가?"
- **세로 비교(퍼널 분석):** "사용자들이 어디서 많이 이탈하는가?"
- 둘을 함께 보면 **"B가 좋다"뿐 아니라 "왜(어느 단계에서) 좋은가"**까지 알 수 있음.

---

## 1. 데이터셋 두 개 (Datasets)

| 데이터셋 | 출처 | 관점 | 주요 내용 |
|---|---|---|---|
| `meta_ads_data.csv` | 광고 플랫폼(Meta) | 광고주 관점 | 노출, 클릭, 비용, Meta 픽셀 구매 |
| `ga4_landing_page_data.csv` | 웹사이트(GA4) | 사용자 행동 | 세션, 장바구니, 실제 구매, 머문 시간 |

**왜 두 개를 합치나 (가장 중요한 개념):**
Meta와 GA4의 **구매 숫자는 보통 다릅니다.**

- **Meta**: 클릭 직후 발생한 전환을 광고에 귀속(attribution) → 실제보다 후하게 잡히는 경향
- **GA4**: 사이트에서 **실제 주문 완료**된 것만 카운트 → 더 보수적

그래서 둘을 합쳐야 "광고비(Meta) → 실제 매출(GA4)"의 **더 정확한 그림**을 그릴 수 있습니다. 한쪽만 보면 반쪽짜리 분석이 됩니다.

---

## 2. 핵심 연결 키 — `join_key`

두 데이터를 1:1로 붙이는 **인공적인 고유 식별자**입니다. Meta와 GA4는 서로 다른 시스템에서 나오기 때문에, 단순히 날짜나 캠페인 ID만으로는 "이 광고 클릭 → 이 웹사이트 방문"을 정확히 연결하기 어렵습니다.

### 생성 규칙

```python
join_key = f"{date}_{campaign_id}_{ad_id}_{ab_variant}"
```

예시:
```
20260101_238100000001_238100200001_A_Control
```

### 구성 요소

| 부분 | 의미 | 예시 값 | 출처 |
|---|---|---|---|
| `date` | 날짜 (YYYYMMDD) | `20260101` | Meta: `date_start`, GA4: `date` |
| `campaign_id` | 캠페인 ID | `238100000001` | Meta & GA4 공통 |
| `ad_id` | 개별 광고 소재 ID | `238100200001` | Meta & GA4 공통 |
| `ab_variant` | A/B 테스트 그룹 | `A_Control` 또는 `B_Variant` | Meta & GA4 공통 |

같은 `join_key`를 가진 행끼리 합쳐지므로, **같은 날짜 + 같은 광고 + 같은 A/B 그룹**의 데이터가 정확히 매칭됩니다.
`ab_variant`를 키에 포함하기 때문에 **같은 광고를 A/B 두 버전으로 동시에 돌려도** 깔끔하게 구분됩니다.

### 실제로는 언제 만들어지나?

- Meta CSV와 GA4 CSV **둘 다 이미 `join_key` 컬럼을 가진 채로** 나옵니다 (ETL/데이터 준비 단계에서 생성).
- 파이썬 분석 스크립트(`generate_report.py`)는 단순히 `on="join_key"`로 **merge만** 하면 됩니다.
- GA4는 `campaign_id`, `ad_id`, `ab_variant` 전용 컬럼을 기본 제공하지 않으므로, **URL 쿼리 문자열을 파싱**해서 별도 컬럼으로 추출합니다 (BigQuery/Python/코스 데이터 준비 과정).

```python
# GA4 데이터에서 join_key 생성 예시
ga4['join_key'] = (
    ga4['date'].astype(str).str.replace('-', '') + '_' +   # 날짜
    ga4['campaign_id'].astype(str) + '_' +                  # campaign_id
    ga4['ad_id'].astype(str) + '_' +                        # ad_id
    ga4['ab_variant']                                        # A_Control / B_Variant
)
# Meta 쪽도 동일 로직
```

### merge 코드

```python
ab = pd.merge(
    meta,
    ga4,
    on="join_key",
    how="inner"   # ← 반드시 inner (아래 참고)
)
```

이렇게 연결하면 한 행에 **광고 비용(spend) + 실제 구매(ecommercePurchases)** 정보가 함께 들어갑니다.

---

## 3. Meta Ads 계층 구조 — Campaign ID vs Ad ID

`join_key`의 `campaign_id`, `ad_id`를 제대로 이해하려면 Meta의 3계층 구조를 알아야 합니다.

```
Campaign (캠페인)          ← 최상위(부모)
   └── Ad Set (광고 세트)   ← 중간: 타겟팅, 예산, 배치 관리
         └── Ad (광고)      ← 최하위(자식): 실제로 사용자에게 보이는 개별 소재
```

| ID 종류 | 의미 | 역할 예시 |
|---|---|---|
| **Campaign ID** | 캠페인 전체를 대표 | "LP_AB_Test_Prospecting" 캠페인 |
| **Ad Set ID** | 타겟팅·예산·배치 관리 | "Broad Audience" 세트 |
| **Ad ID** | 사용자에게 보이는 개별 광고 | "UGC_Testimonial" 크리에이티브 |

**구체적 예시:**
```
Campaign ID: 238100000001 (LP_AB_Test_Prospecting)
  ├─ Ad Set 1 (238100001001)
  │    ├─ Ad ID 238100200001 → A_Control_UGC_Testimonial
  │    └─ Ad ID 238100200002 → A_Control_Static_Product_Benefit
  └─ Ad Set 2 (238100001002)
       └─ Ad ID 238100200007 → B_Variant_UGC_Testimonial
```

**실무에서 왜 중요한가:**

- **Campaign ID로 보면** → 전체 캠페인 성과
- **Ad ID로 보면** → 개별 크리에이티브 성과 (**A/B 테스트의 핵심**)
- A/B 테스트는 주로 **Ad ID 단위로 B 버전(새 크리에이티브/랜딩페이지)을 만들어 비교**합니다.

---

## 4. Join은 반드시 `inner` — `left`는 위험 ⚠️

노트가 특별히 강조하는 **함정 포인트**입니다.

### 문제 상황

Meta 테이블에 GA4 짝이 없는 행(=**고스트 행**, 예: 클릭은 있었지만 사이트에 도착 못 함)이 있을 때:

- `how='left'` → Meta의 모든 행이 살아남고, 짝 없는 행의 GA4 컬럼(`sessions`, `addToCarts` 등)은 전부 **NaN**이 됨.
- `how='inner'` → **양쪽에 모두 있는 행만** 남음 (예: 9개).

### `left`가 왜 위험한가

- NaN이 섞이면 `spend / sessions = NaN` → **ROAS 계산이 깨짐**
- `groupby().sum()` 집계 시 NaN이 조용히 무시되어 **숫자가 틀릴 수 있음**
- 에러 메시지가 없어서 **버그를 찾기 어려움**

### `inner`를 추천하는 이유

- 양쪽 테이블에 모두 존재하는 행만 유지
- GA4 컬럼에 NaN이 절대 안 생김
- CVR, ROAS 계산이 항상 유효
- 고스트 행은 조용히 제거됨 (데이터 누수 없음)

> **정리:** 코드에서 `how='left'`를 `how='inner'`로 바꾸면 NaN 위험이 사라집니다.

---

## 5. 분석 파이프라인 5단계

1. **데이터 로드 & 결합** (`inner join`)
2. **JSON 파싱** — Meta의 `actions`, `action_values` 컬럼(JSON 블롭)을 숫자 컬럼으로 변환
3. **그룹별 집계** (A vs B) — `ab_variant`로 groupby 후 `spend`, `clicks`, `sessions`, `conversions`, `revenue` 등 합계
4. **파생 지표 계산** — CVR, ROAS, CPC, CPM, cost-per-ATC, 퍼널 드롭률
5. **통계적 유의성 검정**

---

## 6. 주요 분석 지표 (Metrics)

지표는 **역할에 따라 두 그룹**으로 나뉩니다. 이 프레임이 노트 전체의 뼈대입니다.

- **Primary Metrics (주요 판단 기준)** — 승패를 결정
  - **GA4 CVR** (전환율) — 가장 중요
  - **ROAS** (광고 수익률)
- **Guardrail Metrics (부작용 확인)** — 나빠지지 않았는지 감시
  - **CPC, CPM, Cost per Add-to-Cart**
- **퍼널 드롭률** — Sessions → Engaged → Add to Cart → Checkout → Purchase

### 지표 정의표

| 지표 | 이름 | 설명 | 방향 |
|---|---|---|---|
| **CVR** | 전환율 | 사이트 방문자 중 실제 구매까지 완료한 비율. 광고가 "구매로 이어지는 힘". | 높을수록 ↑ |
| **ROAS** | 광고 수익률 | 광고비 1원당 매출. 4.0이면 1원 써서 4원 벎. | 높을수록 ↑ |
| **CPC** | 클릭당 비용 | 클릭 1회당 든 비용. 낮을수록 같은 예산으로 더 많은 방문자 유입. | 낮을수록 ↑ |
| **CPM** | 노출 1,000회당 비용 | 1,000명에게 보이는 데 든 비용. 브랜드 인지도처럼 "보여주는 것" 자체가 목적일 때. | 낮을수록 ↑ |
| **Cost per Add-to-Cart** | 장바구니 추가당 비용 | 상품을 장바구니에 담게 유도하는 데 든 광고비. 구매 직전 단계 효율. | 낮을수록 ↑ |
| **Funnel Drop Rate** | 퍼널 이탈률 | 각 단계에서 다음 단계로 못 넘어가고 이탈한 비율. 어느 단계가 병목인지 찾는 용도. | 낮을수록 ↑ |

### 광고 노출 지표 읽는 법 (예시)

| 지표 | 값 | 의미 |
|---|---|---|
| impressions | 2,024 | 광고가 2,024번 노출됨 (같은 사람 중복 포함) |
| reach | 1,143 | 광고를 최소 한 번 본 **순 사용자 수** |
| frequency | 1.77 | 1인당 평균 1.77번 노출 (너무 높으면 피로도 유발) |
| ctr | 1.38% | 광고 본 사람 중 클릭한 비율 |
| inline_link_click_ctr | 1.04% | 실제 링크 클릭만 세는 더 엄격한 CTR |

> A/B **비교의 주력 지표는 CTR과 Frequency**. Impressions/Reach는 규모 참고용.

---

## 7. A/B 테스트 데이터 플로우 (가로 비교)

### 5단계 흐름

1. **Identity & Split (데이터 기반)** — `ab_variant`(A_Control vs B_Variant), `date`, `ad_id`로 행을 식별·분할
2. **Derived Metrics** — 각 `ab_variant`별로 파생 지표 계산
3. **Aggregate by `ab_variant`** — 변형별로 **한 줄의 요약 행** 생성 (총 spend, 총 impressions, 총 purchases, 총 revenue 등)
4. **Statistical Test** — A와 B의 차이가 우연이 아닌지 검정
5. **Verdict** — 최종 판정

### 통계 검정 (매우 중요)

두 종류의 검정을 지표 성격에 맞게 사용합니다.

| 검정 | 대상 지표 | 성격 |
|---|---|---|
| **카이제곱(Chi-squared) / two-proportion z-test** | CVR, CTR | 비율형(전환됨/안 됨 = 이진) |
| **Mann-Whitney U** | 세션당 매출(Revenue per session) | 연속형, 비정규 분포 데이터 |

**판정 기준: `p < 0.05`** → 변형 간 차이가 통계적으로 유의미.

> ⚠️ **p-value는 LLM이 추정하지 않고 실제 검정 함수로 계산**합니다. (프로젝트의 `run_ab_significance_test` 툴 원칙과 동일)

### Guardrail 지표 해석 (CPC / CTR 예시)

- **CPC** = `spend / clicks`. 클릭은 우리 사이트로 들어오는 입구. CPC가 크게 높아지면 = 같은 수의 사람을 데려오는 데 돈을 더 많이 써야 함 → ROAS·CVR이 좋아져도 CPC가 폭등하면 전체 수익성이 나빠질 수 있음.
- **CTR** = `clicks / impressions`. 광고의 매력도와 관련성을 직접 보여줌. CTR이 크게 낮아지면 = 새 크리에이티브/랜딩페이지가 사용자에게 덜 끌린다는 신호. 장기적으로 Meta 알고리즘이 광고를 덜 노출시킬 위험.

---

## 8. 퍼널 분석 (세로 비교)

### 컬럼의 4가지 의미 단위 (chunks)

| 그룹 | 컬럼 | 의미 |
|---|---|---|
| **진입 지점(Entry Point)** | sessionSource, sessionMedium, landingPagePlusQueryString, deviceCategory, country | 어디서 왔고 어떤 페이지에 도착했나 |
| **트래픽 & 참여(Traffic & Engagement)** | totalUsers, activeUsers, sessions / engagedSessions, engagementRate, avgSessionDuration | 얼마나 방문했고 얼마나 잘 참여했나 |
| **퍼널 행동(Funnel Actions)** | addToCarts, checkouts, keyEvents | 퍼널 중간 단계 (browse → cart → checkout) |
| **퍼널 성과(Outcome)** | ecommercePurchases, conversions, totalRevenue | 최종 목표: 확정된 구매 |

> `spend`, `impressions`, `clicks`, `ctr`, `cpc`, `cpm`, `purchase_roas`는 **퍼널 분석에서 제외** — 이 지표들은 "광고 집행" 측면이고, 퍼널은 사용자가 **사이트에 도착한 이후**부터 시작하기 때문.

### 5단계 퍼널

```
광고 클릭 → 사이트 도착
   │
   ▼
1단계 — 세션 시작 (Session started)     드롭률 = 1 − (세션 수 / 클릭 수)
   │
   ▼
2단계 — 참여 세션 (Engaged session)     드롭률 = 1 − 참여율(engagementRate)
   │
   ▼
3단계 — 장바구니 담기 (Add to Cart)      드롭률 = 1 − (장바구니 수 / 세션 수)
   │
   ▼
4단계 — 결제 시작 (Checkout started)     드롭률 = 1 − (결제 시작 수 / 장바구니 수)
   │
   ▼
5단계 — 구매 완료 (Purchase complete)    드롭률 = 1 − (구매 수 / 결제 시작 수)
```

**핵심 아이디어(Key idea):**
각 단계의 수치가 **다음 단계 비율의 분모**가 됩니다. 드롭률(이탈률)이 가장 큰 구간이 가장 먼저 해결해야 할 병목입니다. `ab_variant`별로 퍼널을 따로 실행해서, 변형 간 차이가 어디서 발생하는지 찾습니다.

### GA4 "Engaged Session" 정의

세션이 아래 중 **하나라도** 만족하면 참여 세션으로 표시:
- 10초 이상 지속, **또는**
- 1개 이상의 key event (conversions, add_to_cart 등), **또는**
- 2개 이상의 페이지뷰/스크린뷰

### 워크된 예시 (GA4 1행, 2026-01-01)

| 단계 | 계산 | 값 | 드롭률 |
|---|---|---|---|
| 1. Session started | 1 − (sessions/clicks) | sessions=15, clicks=28 | 46.4% |
| 2. Engaged session | 1 − (engaged/sessions) | engaged=10, sessions=15 | 33.3% |
| 3. Add to cart | 1 − (addToCarts/sessions) | addToCarts=1, sessions=15 | **93.3%** ← 최대 병목 |
| 4. Checkout started | 1 − (checkouts/addToCarts) | checkouts=1, addToCarts=1 | 0.0% |
| 5. Purchase complete | 1 − (purchases/checkouts) | purchases=1, checkouts=1 | 0.0% |

**Overall CVR (top→bottom)** = ecommercePurchases / sessions = 1/15 = **6.67%**

> Add to Cart 단계(93.3% 드롭)가 가장 큰 문제 → 랜딩 페이지가 가장 개선이 필요한 지점. (실제 캠페인에서 1단계 드롭률은 흔히 30~60% 수준)

---

## 9. 실제 A/B 리포트 결과 (LP_AB_Test_Prospecting)

> 캠페인: LP_AB_Test_Prospecting · 기간: 2026-01-01 ~ 2026-01-09
> **결론: B — Variant 압승** → 예산을 B로 이동 추천

### 9-1. Primary & secondary metrics

**PRIMARY METRICS — GO / NO-GO 결정의 핵심**

| 지표 | A (Control) | B (Variant) | Δ Lift | 유의성 | 의미 |
|---|---|---|---|---|---|
| **CVR (GA4)** | 1.19% | **2.10%** | **+76.3%** | Significant (p=0.00) | 세션당 구매 전환율 (거의 2배) |
| **ROAS** | 2.39x | **4.55x** | **+90.1%** | Significant (p=0.00) | 광고비 1원당 수익 (거의 2배) |
| **Cost per purchase (GA4)** | $71.94 | **$32.38** | **−55.0%** | n/a | 구매 1건당 실제 비용 (절반 이하) |

→ Primary 지표 3개 **모두 B가 압도적**. 같은 돈으로 2배 이상 구매를 만들어냄.

**GUARDRAIL METRICS — 부작용 감시**

| 지표 | A | B | Δ Lift | 유의성 | 해석 |
|---|---|---|---|---|---|
| **CPC** | $0.56 | **$0.44** | **−21.8%** | Significant | 클릭 비용이 오히려 줄어듦 → 좋음 |
| **CPM** | $8.19 | $9.01 | +10.0% | n/a | 소폭 상승, 큰 문제 아님 ("higher-intent audience") |
| **Cost per add-to-cart** | $16.60 | **$8.09** | **−51.3%** | Significant | 장바구니까지 데려오는 비용 절반 가까이 감소 |

→ Guardrail 지표도 **B가 나쁘지 않거나 더 좋음** → "B를 확대해도 안전하다"는 근거.
(CPM만 소폭 올랐지만, 이는 더 구매 의도 높은(higher-intent) 좁은 타겟을 노렸을 때 예상되는 현상)

**FUNNEL DROP RATES — 어느 단계에서 이탈하나**

| 단계 | A 드롭률 | B 드롭률 | 해석 |
|---|---|---|---|
| Click → Session | 35.0% | 35.9% | 클릭 후 실제 도착 비율 (비슷) |
| Session → Engaged | 43.3% | **36.2%** | 참여 품질 B가 더 좋음 |
| Engaged → Add to Cart | 94.8% | **91.8%** | **가장 큰 문제 구간(의도 단계)**, B가 조금 개선 |
| Add to Cart → Checkout | 56.8% | 57.3% | 비슷 |
| Checkout → Purchase | 46.6% | **41.8%** | B가 조금 더 좋음 |

→ Engaged → Add to Cart 단계 드롭률이 **90% 이상**으로 현재 최대 병목. B가 이 단계 개선이 가장 두드러짐.

### 9-2. Visual analysis (차트 6종)

- **Primary Metrics 막대 2개** (CVR, ROAS): B가 두 지표 모두 훨씬 높은 막대 → 차이의 크기를 직관적으로 전달.
- **Funnel Drop 막대**: 단계별 사용자 수 비교 + 단계 간 드롭률 주석. Add to Cart 개선이 B의 주요 강점임을 시각화.
- **Spend vs ROAS 산점도**: 점 하나 = 하루. B(초록)가 전반적으로 ROAS 더 높고 위쪽 분포 → "운이 아니라 기간 내내 일관되게 좋았다".
- **Cost Efficiency 막대 3개** (CPC, CPM, Cost per ATC): 낮을수록 좋은 지표들, B가 CPC·Cost per ATC에서 우수.
- **Daily Trends 선그래프** (CVR & ROAS): B 라인이 전체적으로 위 + 안정적 → 단기적 운이 아닌 안정적 우위 증명.
- **Funnel Drop-Rate Heatmap**: 빨강=높은 드롭(문제), 초록=낮은 드롭. **Add to Cart 단계가 두 버전 모두 진한 빨강** → 가장 시급한 개선 지점.

### 9-3. Funnel counts (절대 규모)

| 단계 | A — Control | B — Variant | Δ Lift | 의미 |
|---|---|---|---|---|
| Ad clicks (Meta) | 3,263,015 | 21,616,370 | +562.5% | 광고 클릭 수 |
| Sessions (GA4) | 2,123,315 | 13,856,335 | +553.3% | 실제 방문 세션 수 |
| Engaged sessions | 1,203,550 | 8,836,290 | +634.2% | 제대로 참여한 세션 |
| Add to cart | 109,615 | 1,166,300 | **+964.0%** | 장바구니 담은 횟수 |
| Checkout started | 47,395 | 498,580 | +952.0% | 결제 시작 횟수 |
| Purchase complete | 25,295 | 291,265 | **+1051.5%** | 실제 구매 완료 횟수 |

**핵심:**
- B가 광고 클릭 수 약 **6.6배** → 모든 단계에서 절대 숫자가 압도적.
- 이는 "B가 운이 좋았다"가 아니라 **B가 더 많은 트래픽을 끌어들였고, 그 트래픽이 더 잘 전환됐다**는 의미.
- **Lift(개선율)가 단계가 내려갈수록 커짐** (562% → 1051%) → 특히 Add to Cart·Purchase 단계에서 개선 폭이 훨씬 큼.
- 비율(%)도 중요하지만 **실제 규모(절대값)도 매우 중요** (예: 10% 개선 vs 1000% 개선 + 실제 구매 수 10배).

### 9-4. Conclusion & next actions

**전체 결론:** B — Variant가 A — Control보다 명확히 우수 → **B 확대 추천.**

주요 근거:
- Primary Metrics(CVR, ROAS, Cost per purchase)에서 B가 크게 앞섬
- Guardrail Metrics(CPC, CPM, Cost per ATC)에서도 B가 나쁘지 않거나 더 좋음
- 특히 Add to Cart 단계 개선이 가장 두드러짐
- 통계적으로도 유의미한 차이 (p=0.00)

**통계 방법론 노트 (Kohavi et al. 프레임):**
많은 회사가 "모든 지표를 합쳐 하나의 점수(OEC, composite weighted score)"를 만들려 하지만, 이 리포트는 그 방식을 **추천하지 않음**. 대신 두 규칙을 따름:
- Primary Metrics(CVR, ROAS)가 긍정적으로 움직이고,
- Guardrail Metrics가 크게 나빠지지 않았다면 → **B를 승자로 판정**.
- 이유: 더 명확하고 실무 의사결정이 쉬움.

**추천 행동(Recommended actions):**

| # | 행동 | 설명 |
|---|---|---|
| 1 | 대부분의 예산을 B로 이동 | 지금 당장 B에 더 많은 돈을 투입 |
| 2 | 추가 7일 더 테스트 진행 | 통계 신뢰도 확보 (목표: 변형당 구매 50건 이상) |
| 3 | **Checkout → Purchase 단계 개선** | A·B 모두 여전히 큰 드롭 발생. A/B 테스트와 **별개로** 최적화 필요 |

> **3번이 특히 중요:** Add to Cart는 B가 많이 개선했지만, 결제 완료 단계는 두 버전 모두에서 큰 손실 발생 → A/B와 무관한 별도 과제.

**한 줄 요약:**
> B Variant가 Primary 지표와 퍼널 모두에서 우수했고, Guardrail 지표도 안전한 수준이므로, **예산을 B로 집중**하고, 추가 테스트를 진행하면서 **Checkout 단계 개선을 병행**하는 것이 좋다.

---

## 10. 이 셋업을 직접 재현하는 법

### Phase 1 — Core Tracking Setup

**Meta Ads 쪽**
1. Events Manager → 새 Pixel 생성
2. Meta Pixel을 웹사이트에 설치 (Google Tag Manager 권장)
3. **Conversions API** 활성화 (강력 권장)
4. Standard Events 설정: `AddToCart`, `InitiateCheckout`, `Purchase`
5. 이벤트 코드에 **항상** 파라미터 전송:

```javascript
fbq('track', 'AddToCart', {
  content_ids: ['PROD123'],
  content_type: 'product',
  value: 89.99,
  currency: 'USD',
  custom_data: { ab_variant: 'A_Control' }   // A/B에 유용
});
```

**GA4 쪽**
1. Enhanced Ecommerce 활성화
2. 표준 이벤트명 사용: `add_to_cart`, `begin_checkout`, `purchase`
3. rich data 전송:

```javascript
gtag("event", "add_to_cart", {
  currency: "USD",
  value: 89.99,
  items: [{ item_id: "PROD123", item_name: "...", price: 89.99, quantity: 1 }]
});
```

### Phase 2 — A/B Testing Setup (join_key의 핵심)

**`ab_variant` 전달 방법:** 랜딩 페이지 URL에 쿼리 파라미터로 추가
- A 버전: `https://yoursite.com/landing?variant=a`
- B 버전: `https://yoursite.com/landing?variant=b`

양쪽 시스템에서 캡처:

```javascript
// GA4 (GTM 또는 gtag)
const urlParams = new URLSearchParams(window.location.search);
const abVariant = urlParams.get('variant') || 'unknown';
gtag("set", "user_properties", { ab_variant: abVariant });

// Meta Pixel
fbq('track', 'AddToCart', {
  custom_data: { ab_variant: abVariant }
});
```

### Phase 3 — Backend / Data Pipeline (join_key 생성, 저자의 비법)

```python
def build_join_key(row):
    date_str = pd.to_datetime(row['date']).strftime('%Y%m%d')
    return f"{date_str}_{row['campaign_id']}_{row['ad_id']}_{row['ab_variant']}"

# Meta, GA4 양쪽 데이터프레임에 적용
meta['join_key'] = meta.apply(build_join_key, axis=1)
ga4['join_key']  = ga4.apply(build_join_key, axis=1)
```

→ 이 `join_key`로 daily CSV를 export.

### 전체 데이터 수집 흐름 (잠재고객 클릭 → GA4 백엔드)

```
[Meta Ads Manager] 광고 생성 → Tracking → URL Parameters 설정
   ↓ Final URL 자동 생성 (utm_source/medium/campaign + utm_content=A_Control ← A/B 구분)
Bob 클릭 → 랜딩 페이지 도착 (/landing/ab-test?...)
   ├─ GA4 태그: 세션·landingPagePlusQueryString·addToCart·checkout·purchase 수집
   └─ Meta Pixel(또는 CAPI): ViewContent·AddToCart·Purchase 기록, ad_id로 Meta 측 귀속
   ↓ 두 시스템에 데이터 저장 (Meta: spend/clicks/impressions | GA4: sessions/funnel/revenue)
일일 Export + ETL → join_key 생성 → Python 분석(generate_report.py)
   → pd.merge(on="join_key") → 지표 계산 → 리포트 생성
```

### Full Recommended Stack (2026 기준)

| 레이어 | 도구 / 방법 | 목적 |
|---|---|---|
| Frontend Tracking | Google Tag Manager + gtag/fb pixel | 이벤트 발생 |
| Server-side | Conversions API + custom backend | 신뢰성 있는 데이터 |
| A/B Variant | Query param + custom dimension | 조인 가능하게 |
| Data Warehouse | BigQuery / Snowflake | raw 이벤트 저장 |
| Daily Export | Python ETL script | CSV 생성 |
| (Future) 시각화 | **Looker Studio** | 대시보드 |

### E-Commerce Performance Calculator (Looker Studio 공식)

| 분류 | 지표 | 예시 결과 | Looker Studio 공식 |
|---|---|---|---|
| Core | ROAS | 3.36x | `SUM(Revenue) / SUM(Spend)` |
| Core | Revenue | $8,400.00 | `SUM(Revenue)` |
| Core | Orders | 95 | `SUM(Orders)` |
| Efficiency | CPA | $26.32 | `SUM(Spend) / SUM(Orders)` |
| Efficiency | AOV | $88.42 | `SUM(Revenue) / SUM(Orders)` |
| Efficiency | CPM | $20.83 | `(SUM(Spend) / SUM(Impressions)) × 1000` |
| Efficiency | CPC | $0.81 | `SUM(Spend) / SUM(Link Clicks)` |
| Blended | CTR | 2.58% | `SUM(Link Clicks) / SUM(Impressions)` |
| Blended | CVR (Session) | 3.39% | `SUM(Orders) / SUM(Sessions)` |
| Blended | CVR (Click) | 3.06% | `SUM(Orders) / SUM(Link Clicks)` |
| Blended | Rev / 1k Imp | $70.00 | `(SUM(Revenue) / SUM(Impressions)) × 1000` |

---

## 11. `da_agent` 프로젝트에 적용할 시사점

- 이 노트의 **Primary + Guardrail 프레임**과 **카이제곱 / Mann-Whitney U 검정**은 `kpi_dictionary.md` 및 `run_ab_significance_test` 툴 정의와 정확히 일치 → 지표 정의의 SSOT 근거로 활용 가능.
- `join_key` 스키마(`date_campaignid_adid_abvariant`)는 `ab_test_mart`의 `join_key`, `date × variant` 구조와 동일 → Mart 설계 검증 자료.
- **p-value는 LLM이 추정 금지, 검정 툴로만 계산**하는 원칙이 노트에서도 반복 강조됨 → Data Scientist 노드의 가드레일과 부합.
- 퍼널 5단계(Sessions→Engaged→Add to Cart→Checkout→Purchase)는 `funnel_mart` 정의와 매핑해 일관성 점검 권장.

---

*이 문서는 원본 스터디 노트(주정민/JU DATA)를 재구성한 요약본입니다. 수치·공식은 원본 리포트 값을 그대로 옮겼습니다.*
