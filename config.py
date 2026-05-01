# ══════════════════════════════════════════════
# 클릭 방식 설정
# ══════════════════════════════════════════════
# "directinput" | "sendinput" | "mousekeys"
CLICK_METHOD = "sendinput"

# ══════════════════════════════════════════════
# 이미지 인식 설정
# ══════════════════════════════════════════════
DETECT_CONFIDENCE = 0.55     # 몬스터 감지 임계값 (0.0 ~ 1.0)
TRACKING_CONFIDENCE = 0.40   # 추적 중 ROI 재탐색 임계값 (감지보다 낮게 — 반투명 대응)
SEARCH_INTERVAL = 0.5        # 이미지 탐색 주기 (초)

# 멀티스케일 탐색 범위 (적을수록 빠름)
DETECT_SCALES = (0.9, 1.0, 1.1)  # 전체 프레임 탐색용 (3개)
ROI_DETECT_SCALES = (0.95, 1.0, 1.05)  # ROI 재탐색용 소폭 스케일 (3개)

# ══════════════════════════════════════════════
# 에지 기반 보조 감지 설정 (반투명 몬스터 대응)
# ══════════════════════════════════════════════
EDGE_DETECT_ENABLED = True           # 에지 매칭 보조 감지 활성화
EDGE_DETECT_CONFIDENCE = 0.35        # 에지 매칭 임계값 (그레이보다 낮게)
EDGE_CANNY_LOW = 50                  # Canny 에지 하한 임계값
EDGE_CANNY_HIGH = 150                # Canny 에지 상한 임계값
EDGE_ONLY_MAX_COUNT = 5              # 에지 전용 연속 감지 최대 허용 횟수 (초과 시 추적 해제)

# ══════════════════════════════════════════════
# 반투명 템플릿 변형 설정 (ROI 전용)
# ══════════════════════════════════════════════
TRANSPARENT_VARIANTS_ENABLED = True  # 반투명 템플릿 자동 생성
TRANSPARENT_ALPHA_LEVELS = (0.3, 0.5, 0.7)  # 블렌딩 비율 (1.0=원본, 0.3=70% 투명)
TRANSPARENT_BG_COLORS = (            # 블렌딩 대상 배경색 (BGR) — 다중 배경 지원
    (35, 70, 25),                    # 짙은 녹색 (나무 잎사귀)
    (70, 110, 50),                   # 연한 녹색 (풀밭/밝은 잎)
)

# ══════════════════════════════════════════════
# UI 제외 영역 (게임 화면 내 비탐색 구간)
# ══════════════════════════════════════════════
# 프레임 상단 N px 제외 (캐릭터 초상화, HP바, 미니맵 등)
UI_EXCLUDE_TOP = 130
# 프레임 하단 N px 제외 (채팅창, 스킬바, 인벤토리 등)
# 밝기 필터 — 감지 영역 평균 밝기가 이 값 이상이면 배경 오탐으로 제거
BRIGHTNESS_REJECT_THRESHOLD = 170   # 0~255 (흰색 안개/폭포/하늘 배경 제거용, 기존 200에서 하향)
UI_EXCLUDE_BOTTOM = 140

# ══════════════════════════════════════════════
# 전투 판정 설정
# ══════════════════════════════════════════════
DETECT_MISS_MAX = 4              # 연속 N회 감지 실패 시 사망 판정 (기존 3 → 4로 증가)
TARGET_TIMEOUT = 15.0        # 동일 대상 최대 공격 시간 (초). 초과 시 타겟 전환
HP_CHECK_INTERVAL = 3.0      # HP바 변화 확인 주기 (초)
HP_NO_CHANGE_MAX = 3         # HP 변화 없음 연속 N회 시 타겟 전환
HP_BAR_OFFSET_Y = -20        # 몬스터 bbox 상단에서 HP바까지의 Y 오프셋 (음수=위)
HP_BAR_HEIGHT = 8            # HP바 영역 높이 (px)
# 몬스터 HP바 색상 (빨간색 2구간 — HSV에서 빨강은 양쪽 끝에 걸침)
HP_BAR_COLOR_LOWER1 = (0, 100, 100)    # 빨간색 하위 범위 H=0~10
HP_BAR_COLOR_UPPER1 = (10, 255, 255)
HP_BAR_COLOR_LOWER2 = (170, 100, 100)  # 빨간색 상위 범위 H=170~180
HP_BAR_COLOR_UPPER2 = (180, 255, 255)

# ══════════════════════════════════════════════
# 아이템 줍기 설정
# ══════════════════════════════════════════════
LOOT_ENABLED = True              # 아이템 줍기 활성화
LOOT_KEY_SCANCODE = 0x39         # Spacebar 스캔코드
LOOT_PRESS_COUNT = 2             # Spacebar 입력 횟수
LOOT_PRESS_INTERVAL = 0.10       # 입력 간 간격 (초)
LOOT_DELAY_AFTER_KILL = 0.20     # 사망 판정 후 줍기까지 대기 (초)

# ── 시각 기반 픽업 (Frame Diff) ──
LOOT_VISUAL_ENABLED = True              # 차분 기반 픽업 활성화
LOOT_ROI_EXPAND_RATIO = 1.0             # bbox 크기 대비 ROI 확장 비율 (1.0 = 좌우상하 bbox 1개씩)
LOOT_CORPSE_MASK_RATIO = 1.0            # bbox 마스킹 비율 (1.0 = bbox 전체 영역 무시 — 시체 차분 제거)
LOOT_DIFF_THRESHOLD = 30                # 차분 그레이값 임계값 (0~255)
LOOT_MIN_BLOB_AREA = 30                 # 최소 블롭 면적 (px²) — 노이즈 컷
LOOT_MAX_BLOB_AREA = 2500               # 최대 블롭 면적 (px²) — 큰 객체 컷
LOOT_MAX_DISTANCE_RATIO = 1.5           # bbox 중심에서 블롭 중심까지 허용 거리 (× bbox 대각선 길이)
LOOT_MAX_TOTAL_DIFF_RATIO = 0.6         # ROI 픽셀 대비 차분 비율 상한 (실측 사이클 ~1s × 4 misses 동안 카메라/캐릭터 이동 누적 허용)
LOOT_SNAPSHOT_MAX_AGE = 8.0             # 베이스라인 최대 허용 나이 (초). 실측: TRACK_KILLED까지 4-7s 소요
LOOT_AFTER_CLICK_DELAY = 0.3            # 픽업 클릭 후 대기 (캐릭터 이동/픽업 애니)
LOOT_DEBUG_SAVE = False                 # 차분 디버그 이미지 저장 (튜닝용 — 부담 큼, 평시 False)
LOOT_DEBUG_SAMPLE_RATIO = 0.1           # 디버그 저장 샘플링 비율 (0.1 = 10%만 저장, 1.0 = 전부)
LOOT_DEBUG_DIR = "debug_loot"           # 디버그 이미지 저장 폴더

# ══════════════════════════════════════════════
# 이동 보정 설정
# ══════════════════════════════════════════════
PRECLICK_REFINE_ENABLED = True    # 클릭 직전 ROI 재감지 활성화
PRECLICK_ROI_PAD_RATIO = 0.5     # 클릭 직전 ROI 패딩 비율 (bbox 크기 대비, 작을수록 정확)
TRACKING_ROI_PAD_RATIO = 1.5     # 추적 중 ROI 우선 탐색 패딩 비율 (몬스터 이동 대응, 넓게)
REFINE_MAX_DISTANCE = 40         # 보정 최대 허용 거리 (px). 초과 시 원본 좌표 사용

# ══════════════════════════════════════════════
# 딜레이 설정
# ══════════════════════════════════════════════
DEFAULT_DELAY = 0.3          # 대상 미발견 시 재탐색 대기 시간
ATTACK_INTERVAL = 0.15       # 공격 클릭 후 다음 클릭까지 대기 시간
MIN_CLICK_INTERVAL = 0.1     # 최소 클릭 간격

# ══════════════════════════════════════════════
# 포그라운드 전환 설정
# ══════════════════════════════════════════════
ACTIVATE_WINDOW_ON_START = True   # 매크로 시작 시 게임 창 포그라운드 전환
REACTIVATE_INTERVAL = 5.0        # 주기적 포그라운드 재확인 간격 (초)
REGION_REFRESH_INTERVAL = 30.0   # 게임 창 위치/크기 재확인 간격 (초)

# ══════════════════════════════════════════════
# 몬스터 미발견 시 랜덤 이동 설정
# ══════════════════════════════════════════════
ROAM_ENABLED = True              # 몬스터 미발견 시 랜덤 이동 활성화
ROAM_AFTER_MISS_COUNT = 2        # 연속 N회 미발견 시 이동 시작
ROAM_CLICK_DISTANCE = 250        # 화면 중앙으로부터 클릭 거리 (px)
ROAM_MOVE_DELAY = 1.0            # 이동 클릭 후 도착 대기 시간 (초)
ROAM_DIRECTION_COUNT = 8         # 이동 방향 수 (8방향)

# ══════════════════════════════════════════════
# 캐릭터 HP 물약 자동 사용 설정
# ══════════════════════════════════════════════
POTION_ENABLED = True            # 자동 물약 활성화
POTION_KEY_SCANCODE = 0x02       # 물약 키 스캔코드 (0x02 = 숫자 1키)
POTION_HP_THRESHOLD = 0.5        # HP가 이 비율 이하이면 물약 사용 (0.0~1.0)
POTION_COOLDOWN = 3.0            # 물약 사용 후 재사용 대기 (초)
POTION_CHECK_INTERVAL = 1.0      # HP 확인 주기 (초)

# 캐릭터 HP바 위치 (게임 창 클라이언트 영역 기준 상대 좌표)
# 게임마다 다르므로 실제 HP바 위치에 맞게 조정 필요
# (x, y, w, h) — 게임 화면 좌상단 기준
PLAYER_HP_BAR_REGION = (115, 20, 190, 13)  # 좌상단 캐릭터 초상화 옆 HP바
PLAYER_HP_COLOR_LOWER = (0, 100, 100)    # HP바 HSV 하한 (빨간색 계열)
PLAYER_HP_COLOR_UPPER = (10, 255, 255)   # HP바 HSV 상한
# 빨간색은 HSV에서 H=0~10 또는 H=170~180 범위
PLAYER_HP_COLOR_LOWER2 = (170, 100, 100) # HP바 HSV 하한2 (빨간색 상위 범위)
PLAYER_HP_COLOR_UPPER2 = (180, 255, 255) # HP바 HSV 상한2

# ══════════════════════════════════════════════
# 캐릭터 MP바 위치 및 색상 설정
# ══════════════════════════════════════════════
PLAYER_MP_BAR_REGION = (115, 42, 190, 10)   # MP바 위치 (x, y, w, h) — HP바 아래
PLAYER_MP_COLOR_LOWER = (100, 80, 80)     # MP바 HSV 하한 (파란색 계열)
PLAYER_MP_COLOR_UPPER = (130, 255, 255)   # MP바 HSV 상한
PLAYER_MP_COLOR_LOWER2 = (130, 80, 80)    # MP바 HSV 하한2 (보라색 그라데이션 대응)
PLAYER_MP_COLOR_UPPER2 = (160, 255, 255)  # MP바 HSV 상한2

# ══════════════════════════════════════════════
# 매크로 시작/종료 단축키
# ══════════════════════════════════════════════
START_KEY = "F5"
STOP_KEY = "F6"

# ══════════════════════════════════════════════
# 게임 창 설정
# ══════════════════════════════════════════════
GAME_WINDOW_TITLE = "온라인삼국지"

# 게임 창 영역 자동 감지 사용 여부
# True  → window_manager로 창 위치/크기 자동 획득
# False → MANUAL_REGION 값을 수동으로 지정
AUTO_DETECT_WINDOW = True

# AUTO_DETECT_WINDOW = False 일 때 사용할 수동 영역 (x, y, w, h)
MANUAL_REGION = None  # 예: (0, 0, 1920, 1080)

# ══════════════════════════════════════════════
# 로그 설정
# ══════════════════════════════════════════════
LOG_DIR = "logs"
LOG_LEVEL = "DEBUG"          # DEBUG | INFO | WARNING | ERROR
