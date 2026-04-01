# 프로젝트 핸드오프 문서

> 최종 업데이트: 2026-04-01

## 프로젝트 개요

온라인삼국지2 전용 매크로. 화면 캡처 기반 이미지 인식(템플릿 매칭) + SendInput 클릭으로 몬스터 사냥 자동화. Windows 전용. PyQt6 기반 UI 포함.

---

## 아키텍처 (현재)

```
macro_ui.py          ─ PyQt6 GUI (모니터링/설정/템플릿/통계/트레이)
├── main.py          ─ 콘솔 모드 진입점 (F5/F6 핫키)
├── macro_engine.py  ─ 사냥 루프: 감지 → 클릭 → 줍기 → 반복
├── monster_tracker.py ─ 멀티스케일 템플릿 매칭 + ROI 재탐색
├── screen_capture.py  ─ 공통 캡처 레이어 (dxcam 우선, mss 폴백)
├── image_finder.py  ─ 범용 이미지 탐색 (색상/그레이/ORB)
├── clicker.py       ─ SendInput 하드웨어 클릭 + 키보드 입력
├── window_manager.py ─ 게임 창 탐색 + 포그라운드 전환 + 클라이언트 영역
├── config.py        ─ 모든 설정 상수
└── logger.py        ─ 콘솔+파일 이중 로거
```

---

## 완료된 작업

### Phase 1: 핵심 로직 수정 (커밋 `e3f72ab`)
- `TRACK_MISS_PENDING` 상태 도입 — 유령 클릭 제거
- 몬스터 HP바 색상: H=0~80 → 빨간색 2구간 (H=0~10, H=170~180)
- ROI 멀티스케일 (0.95, 1.0, 1.05) + INTER_AREA/LINEAR 보간법 분리

### Phase 2: 사이클 속도 최적화 (커밋 `95c7e39`)
- `screen_capture.py` 공통 캡처 레이어 신규 생성
- dxcam (Desktop Duplication API, 100+ FPS) + mss 자동 폴백
- 좌우 반전 템플릿 자동 생성 (8→6장)

### Phase 3: 코드 정리 (커밋 `c34b899`)
- CSRT 데드코드 ~100줄 제거
- `self.tracking` → `self.has_target` 리네이밍
- `_local_to_screen()`, `_bbox_center_screen()` 좌표 헬퍼
- hwnd 검증 + 30초마다 region 자동 재획득
- `clear_template_cache()` 명시적 캐시 무효화

### UI 구현 (커밋 `3b76183`)
- PyQt6 기반 다크 테마 UI (기능 1~9)
- 모니터링, 설정, 템플릿 관리 3탭
- 실시간 게임 미리보기 + bbox 오버레이
- 시스템 트레이 최소화

### 버그 수정
- `60b2e2e` — UI 시작 오류 (미구현 시그널, DPI 중복)
- `7187c26` — dxcam region 캡처 좌표 클램핑 + 동적 해상도
- `4e39808` — 클릭 직전 게임 창 포그라운드 전환 (UI 가로채기 방지)
- `5566d1d` — UI 창 제목이 게임 창 검색에 매칭되는 버그 (재귀 인식)

---

## 해결된 주요 이슈

| 이슈 | 원인 | 해결 |
|---|---|---|
| 클릭이 게임에 안 감 | SetForegroundWindow 미호출 + 관리자 권한 | 매 클릭 전 activate_window() + 관리자 경고 |
| 좌표 ~8px 오차 | GetWindowRect (테두리 포함) | GetClientRect + ClientToScreen |
| 타겟 매번 전환 | 화면 중앙 기준 "가장 가까운" 재선택 | 마지막 추적 위치 기준 + ROI 우선 |
| 감지 ~3초 느림 | BGR 매칭 + 5스케일 × 8템플릿 | GRAY 매칭 + 3스케일 + 좌우반전(6장) + dxcam |
| 유령 클릭 (죽은 위치 클릭) | 1회 실패 → 마지막 위치 계속 클릭 | TRACK_MISS_PENDING → 클릭 중단, 3회 연속 miss → 사망 |
| UI 미리보기 재귀 인식 | UI 제목에 "온라인삼국지" 포함 | 제목 변경 + find_game_window 제외 필터 |

---

## 알려진 제한사항 / 남은 작업

### 아직 안 한 것
- [ ] GetSystemMetrics TTL 캐시 (보류 — 핫플러그 위험)
- [ ] 이미지 피라미드 (50% 축소 탐색) — Phase 2에서 보류, 작은 몬스터 recall 위험
- [ ] 캡처 1회 통합 (refine_position 프레임 재사용) — 이동 몬스터 정확도 트레이드오프
- [ ] 사냥 통계의 처치 수가 실시간 연동 안 됨 (engine→UI 콜백 미구현)

### 환경 의존성
- **관리자 권한 필수** — SendInput이 게임에 전달되려면
- **dxcam**: Direct3D 11 드라이버 필요 (대부분 게임 PC에 있음)
- **듀얼 모니터**: 게임=모니터1(메인), 매크로UI=모니터2(서브)
- **게임 창 모드**: 전체화면은 dxcam 캡처 실패 가능

### 설정 조정 필요 항목
- `PLAYER_HP_BAR_REGION = (70, 48, 150, 8)` — 실제 게임 HP바 위치에 맞게 조정
- `POTION_KEY_SCANCODE = 0x02` — 게임 내 물약 단축키에 맞게 조정
- `DETECT_CONFIDENCE = 0.55` — 오탐/미탐 밸런스 조정

---

## Codex CLI 리뷰 반영 사항

### Phase 1 리뷰
- "1회 실패 즉시 TRACK_KILLED" 대신 TRACK_MISS_PENDING 도입 (오탐 loot 방지)
- HP바 green 범위 제외 (배경 오인 위험)
- 이미지 피라미드는 Phase 2로 이관 (작은 몬스터 recall 저하)

### Phase 2 리뷰
- dxcam region 규약 `(left,top,right,bottom)` 반영
- `grab(new_frame_only=False)` 대신 `grab()` + None 체크 + mss 폴백
- 좌우 반전만 적용, 상하(top/bottom) 통합은 거부 (시점이 다름)
- 캡처 통합은 "옵션화 후 실측"으로 보류

### Phase 3 리뷰
- hwnd 검증 시 region 재계산까지 묶음
- GetSystemMetrics 캐싱은 보류 (모니터 핫플러그 위험)
- INTER_AREA 항목 제거 (Phase 1에서 이미 적용)

---

## 실행 방법

```bash
# GUI 모드 (권장)
python macro_ui.py

# 콘솔 모드
python main.py

# 반드시 관리자 권한으로 실행!
```

---

## 커밋 히스토리

| 커밋 | 설명 |
|---|---|
| `0292225` | 매크로 핵심 로직 대폭 개선 (최초 대규모 수정) |
| `e3f72ab` | Phase 1 — TRACK_MISS_PENDING, HP바 2구간, ROI 멀티스케일 |
| `95c7e39` | Phase 2 — dxcam + 공통 캡처 + 좌우 반전 |
| `c34b899` | Phase 3 — CSRT 제거, 좌표 헬퍼, hwnd 검증 |
| `3b76183` | PyQt6 UI 전체 구현 (1~9) |
| `60b2e2e` | UI 시작 오류 수정 |
| `7187c26` | dxcam region 클램핑 수정 |
| `4e39808` | 클릭 직전 포그라운드 전환 |
| `5566d1d` | UI 창 제목 게임 검색 매칭 버그 수정 |
