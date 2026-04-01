"""
매크로 UI (PyQt6 기반).

기능 1~9:
1. 상태 표시 패널 (동작 상태, 타겟, HP, FPS)
2. 시작/중지/비상정지 버튼
3. 실시간 로그 창 (레벨별 색상)
4. 게임 화면 미리보기 (bbox 오버레이)
5. 설정 패널 (슬라이더로 실시간 조정)
6. 템플릿 관리 (추가/삭제/미리보기)
7. HP바 위치 설정 도구
8. 사냥 통계
9. 시스템 트레이
"""
import sys
import os
import time
import threading
import logging
import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QSlider, QComboBox, QGroupBox,
    QGridLayout, QTabWidget, QListWidget, QListWidgetItem, QFileDialog,
    QSystemTrayIcon, QMenu, QSplitter, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QImage, QPixmap, QColor, QIcon, QAction, QFont

import config
from screen_capture import capture_screen
from monster_tracker import MonsterTracker, detect_wolves, _load_templates, clear_template_cache
from macro_engine import MacroEngine
from window_manager import get_game_region, activate_window


# ══════════════════════════════════════════════
# 로그 핸들러 → UI 시그널 연결
# ══════════════════════════════════════════════

class LogSignalEmitter(QObject):
    log_signal = pyqtSignal(str, str)  # (level, message)


class UILogHandler(logging.Handler):
    """로그를 UI로 전달하는 핸들러."""
    def __init__(self, emitter):
        super().__init__()
        self.emitter = emitter

    def emit(self, record):
        try:
            msg = self.format(record)
            self.emitter.log_signal.emit(record.levelname, msg)
        except Exception:
            pass


# ══════════════════════════════════════════════
# 메인 윈도우
# ══════════════════════════════════════════════

class MacroWindow(QMainWindow):
    preview_signal = pyqtSignal(np.ndarray)  # 미리보기 프레임

    def __init__(self):
        super().__init__()
        self.setWindowTitle("매크로 컨트롤러")
        self.setMinimumSize(900, 700)

        # 매크로 엔진
        self.engine = None
        self.engine_thread = None
        self.region = None

        # 통계
        self._stats = {
            "kills": 0, "potions": 0, "clicks": 0,
            "start_time": 0, "fps": 0.0,
        }
        self._cycle_times = []

        # UI 빌드
        self._build_ui()
        self._setup_log_handler()
        self._setup_tray()
        self._setup_timers()

        # 시그널 연결
        self.preview_signal.connect(self._update_preview)

    # ══════════════════════════════════════════
    # UI 빌드
    # ══════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 상단: 탭 (모니터링 / 설정 / 템플릿)
        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # 탭 1: 모니터링
        monitor_tab = QWidget()
        tabs.addTab(monitor_tab, "모니터링")
        self._build_monitor_tab(monitor_tab)

        # 탭 2: 설정
        settings_tab = QWidget()
        tabs.addTab(settings_tab, "설정")
        self._build_settings_tab(settings_tab)

        # 탭 3: 템플릿 관리
        template_tab = QWidget()
        tabs.addTab(template_tab, "템플릿 관리")
        self._build_template_tab(template_tab)

    def _build_monitor_tab(self, parent):
        layout = QVBoxLayout(parent)

        # ── 상단: 상태 + 미리보기 ──
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(top_splitter, stretch=3)

        # 좌측: 상태 패널 + 버튼 + 통계
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # [1] 상태 표시 패널
        status_group = QGroupBox("상태")
        status_layout = QGridLayout(status_group)

        self.lbl_status = QLabel("대기중")
        self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #888;")
        status_layout.addWidget(QLabel("동작:"), 0, 0)
        status_layout.addWidget(self.lbl_status, 0, 1)

        self.lbl_target = QLabel("없음")
        status_layout.addWidget(QLabel("타겟:"), 1, 0)
        status_layout.addWidget(self.lbl_target, 1, 1)

        self.lbl_fps = QLabel("0.0")
        status_layout.addWidget(QLabel("FPS:"), 2, 0)
        status_layout.addWidget(self.lbl_fps, 2, 1)

        self.hp_bar = QProgressBar()
        self.hp_bar.setRange(0, 100)
        self.hp_bar.setValue(100)
        self.hp_bar.setFormat("HP: %v%")
        self.hp_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #555; border-radius: 3px; text-align: center; }
            QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #cc0000, stop:1 #ff3333); }
        """)
        status_layout.addWidget(QLabel("캐릭터 HP:"), 3, 0)
        status_layout.addWidget(self.hp_bar, 3, 1)

        left_layout.addWidget(status_group)

        # [2] 시작/중지/비상정지 버튼
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 시작 (F5)")
        self.btn_start.setStyleSheet("background: #2d7d2d; color: white; font-size: 14px; padding: 8px;")
        self.btn_start.clicked.connect(self._on_start)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■ 중지 (F6)")
        self.btn_stop.setStyleSheet("background: #555; color: white; font-size: 14px; padding: 8px;")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        btn_layout.addWidget(self.btn_stop)

        self.btn_emergency = QPushButton("⊘ 비상정지")
        self.btn_emergency.setStyleSheet("background: #cc0000; color: white; font-size: 14px; font-weight: bold; padding: 8px;")
        self.btn_emergency.clicked.connect(self._on_emergency)
        btn_layout.addWidget(self.btn_emergency)

        left_layout.addLayout(btn_layout)

        # [8] 사냥 통계
        stats_group = QGroupBox("사냥 통계")
        stats_layout = QGridLayout(stats_group)

        self.lbl_kills = QLabel("0")
        self.lbl_kills.setStyleSheet("font-size: 16px; font-weight: bold; color: #ff6633;")
        stats_layout.addWidget(QLabel("처치 수:"), 0, 0)
        stats_layout.addWidget(self.lbl_kills, 0, 1)

        self.lbl_kph = QLabel("0/h")
        stats_layout.addWidget(QLabel("시간당:"), 1, 0)
        stats_layout.addWidget(self.lbl_kph, 1, 1)

        self.lbl_potions = QLabel("0")
        stats_layout.addWidget(QLabel("물약 사용:"), 2, 0)
        stats_layout.addWidget(self.lbl_potions, 2, 1)

        self.lbl_uptime = QLabel("00:00:00")
        stats_layout.addWidget(QLabel("가동 시간:"), 3, 0)
        stats_layout.addWidget(self.lbl_uptime, 3, 1)

        left_layout.addWidget(stats_group)
        left_layout.addStretch()
        top_splitter.addWidget(left_panel)

        # [4] 우측: 게임 화면 미리보기
        preview_group = QGroupBox("게임 화면 미리보기")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("캡처 대기중...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("background: #1a1a1a; border: 1px solid #333;")
        preview_layout.addWidget(self.preview_label)
        top_splitter.addWidget(preview_group)

        top_splitter.setSizes([300, 500])

        # [3] 하단: 실시간 로그
        log_group = QGroupBox("실시간 로그")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.log_text.setStyleSheet("background: #0d0d0d; color: #ccc; font-family: Consolas; font-size: 11px;")
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group, stretch=1)

    def _build_settings_tab(self, parent):
        """[5] 설정 패널 + [7] HP바 위치 설정."""
        layout = QVBoxLayout(parent)

        # 감지 설정
        detect_group = QGroupBox("감지 설정")
        detect_layout = QGridLayout(detect_group)

        detect_layout.addWidget(QLabel("감지 임계값:"), 0, 0)
        self.slider_confidence = QSlider(Qt.Orientation.Horizontal)
        self.slider_confidence.setRange(30, 90)
        self.slider_confidence.setValue(int(config.DETECT_CONFIDENCE * 100))
        self.lbl_confidence_val = QLabel(f"{config.DETECT_CONFIDENCE:.2f}")
        self.slider_confidence.valueChanged.connect(
            lambda v: (setattr(config, 'DETECT_CONFIDENCE', v / 100),
                       self.lbl_confidence_val.setText(f"{v / 100:.2f}")))
        detect_layout.addWidget(self.slider_confidence, 0, 1)
        detect_layout.addWidget(self.lbl_confidence_val, 0, 2)

        detect_layout.addWidget(QLabel("공격 간격(ms):"), 1, 0)
        self.slider_attack = QSlider(Qt.Orientation.Horizontal)
        self.slider_attack.setRange(50, 500)
        self.slider_attack.setValue(int(config.ATTACK_INTERVAL * 1000))
        self.lbl_attack_val = QLabel(f"{config.ATTACK_INTERVAL * 1000:.0f}ms")
        self.slider_attack.valueChanged.connect(
            lambda v: (setattr(config, 'ATTACK_INTERVAL', v / 1000),
                       self.lbl_attack_val.setText(f"{v}ms")))
        detect_layout.addWidget(self.slider_attack, 1, 1)
        detect_layout.addWidget(self.lbl_attack_val, 1, 2)

        layout.addWidget(detect_group)

        # 물약 설정
        potion_group = QGroupBox("물약 설정")
        potion_layout = QGridLayout(potion_group)

        potion_layout.addWidget(QLabel("HP 임계값(%):"), 0, 0)
        self.slider_potion_hp = QSlider(Qt.Orientation.Horizontal)
        self.slider_potion_hp.setRange(10, 90)
        self.slider_potion_hp.setValue(int(config.POTION_HP_THRESHOLD * 100))
        self.lbl_potion_val = QLabel(f"{config.POTION_HP_THRESHOLD:.0%}")
        self.slider_potion_hp.valueChanged.connect(
            lambda v: (setattr(config, 'POTION_HP_THRESHOLD', v / 100),
                       self.lbl_potion_val.setText(f"{v}%")))
        potion_layout.addWidget(self.slider_potion_hp, 0, 1)
        potion_layout.addWidget(self.lbl_potion_val, 0, 2)

        layout.addWidget(potion_group)

        # 클릭 방식
        click_group = QGroupBox("클릭 방식")
        click_layout = QHBoxLayout(click_group)
        self.combo_click = QComboBox()
        self.combo_click.addItems(["sendinput", "directinput", "mousekeys"])
        self.combo_click.setCurrentText(config.CLICK_METHOD)
        self.combo_click.currentTextChanged.connect(
            lambda v: setattr(config, 'CLICK_METHOD', v))
        click_layout.addWidget(self.combo_click)
        layout.addWidget(click_group)

        # [7] HP바 위치 설정
        hp_group = QGroupBox("캐릭터 HP바 위치 (게임 화면 기준)")
        hp_layout = QGridLayout(hp_group)

        self.hp_inputs = {}
        labels = [("X:", 0), ("Y:", 1), ("W:", 2), ("H:", 3)]
        defaults = config.PLAYER_HP_BAR_REGION
        for (label, idx) in labels:
            hp_layout.addWidget(QLabel(label), 0, idx * 2)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 1920)
            slider.setValue(defaults[idx])
            val_label = QLabel(str(defaults[idx]))
            slider.valueChanged.connect(lambda v, lbl=val_label, i=idx: self._update_hp_region(v, lbl, i))
            hp_layout.addWidget(slider, 0, idx * 2 + 1)
            hp_layout.addWidget(val_label, 1, idx * 2 + 1)
            self.hp_inputs[idx] = slider

        layout.addWidget(hp_group)
        layout.addStretch()

    def _update_hp_region(self, value, label, index):
        label.setText(str(value))
        region = list(config.PLAYER_HP_BAR_REGION)
        region[index] = value
        config.PLAYER_HP_BAR_REGION = tuple(region)

    def _build_template_tab(self, parent):
        """[6] 템플릿 관리."""
        layout = QVBoxLayout(parent)

        # 템플릿 리스트 + 미리보기
        content = QSplitter(Qt.Orientation.Horizontal)

        # 좌: 리스트
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        self.template_list = QListWidget()
        self.template_list.currentRowChanged.connect(self._on_template_select)
        list_layout.addWidget(self.template_list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 추가")
        btn_add.clicked.connect(self._on_template_add)
        btn_row.addWidget(btn_add)

        btn_del = QPushButton("- 삭제")
        btn_del.clicked.connect(self._on_template_delete)
        btn_row.addWidget(btn_del)

        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self._refresh_template_list)
        btn_row.addWidget(btn_refresh)

        list_layout.addLayout(btn_row)
        content.addWidget(list_panel)

        # 우: 미리보기
        self.template_preview = QLabel("이미지를 선택하세요")
        self.template_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.template_preview.setMinimumSize(200, 200)
        self.template_preview.setStyleSheet("background: #1a1a1a; border: 1px solid #333;")
        content.addWidget(self.template_preview)

        layout.addWidget(content)
        self._refresh_template_list()

    # ══════════════════════════════════════════
    # 로그 핸들러
    # ══════════════════════════════════════════

    def _setup_log_handler(self):
        self._log_emitter = LogSignalEmitter()
        self._log_emitter.log_signal.connect(self._append_log)
        handler = UILogHandler(self._log_emitter)
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger("macro").addHandler(handler)

    def _append_log(self, level, message):
        colors = {
            "DEBUG": "#666", "INFO": "#ccc",
            "WARNING": "#ffcc00", "ERROR": "#ff4444", "CRITICAL": "#ff0000",
        }
        color = colors.get(level, "#ccc")
        self.log_text.append(f'<span style="color:{color}">{message}</span>')
        # 자동 스크롤
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ══════════════════════════════════════════
    # [9] 시스템 트레이
    # ══════════════════════════════════════════

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        # 간단한 아이콘 (16x16 컬러 사각형)
        img = QImage(16, 16, QImage.Format.Format_RGB32)
        img.fill(QColor(100, 100, 100))
        self.tray_icon_idle = QPixmap.fromImage(img)
        img.fill(QColor(0, 200, 0))
        self.tray_icon_running = QPixmap.fromImage(img)
        img.fill(QColor(200, 0, 0))
        self.tray_icon_stopped = QPixmap.fromImage(img)

        self.tray.setIcon(QIcon(self.tray_icon_idle))
        self.tray.setToolTip("매크로 - 대기중")

        tray_menu = QMenu()
        action_show = QAction("열기", self)
        action_show.triggered.connect(self.showNormal)
        tray_menu.addAction(action_show)

        action_quit = QAction("종료", self)
        action_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(action_quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        """최소화 시 트레이로 이동."""
        event.ignore()
        self.hide()
        self.tray.showMessage("매크로", "시스템 트레이로 최소화됨", QSystemTrayIcon.MessageIcon.Information, 1500)

    def _quit_app(self):
        self._on_stop()
        self.tray.hide()
        QApplication.quit()

    # ══════════════════════════════════════════
    # 타이머 (미리보기 + 통계 갱신)
    # ══════════════════════════════════════════

    def _setup_timers(self):
        # 미리보기 갱신 (200ms = 5fps)
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self._capture_preview)
        self.preview_timer.start(200)

        # 통계 갱신 (1초)
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start(1000)

    def _capture_preview(self):
        """[4] 게임 화면 캡처 + bbox 오버레이."""
        if self.region is None:
            self.region = get_game_region(config.GAME_WINDOW_TITLE)
        if self.region is None:
            return

        frame = capture_screen(region=self.region)
        if frame is None:
            return

        # 몬스터 감지 결과 오버레이 (엔진이 돌고 있을 때만)
        if self.engine and self.engine.running:
            try:
                wolves = detect_wolves(frame, confidence=config.DETECT_CONFIDENCE)
                for (x, y, w, h, score, name) in wolves:
                    # 감지된 몬스터: 초록 사각형
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(frame, f"{score:.2f}", (x, y - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

                # 현재 타겟 bbox: 빨간 사각형
                if self.engine.tracker.last_bbox:
                    bx, by, bw, bh = self.engine.tracker.last_bbox
                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
            except Exception:
                pass

        self.preview_signal.emit(frame)

    def _update_preview(self, frame):
        """프레임을 QLabel에 표시."""
        h, w, ch = frame.shape
        # 미리보기 크기에 맞춰 리사이즈
        label_w = self.preview_label.width()
        label_h = self.preview_label.height()
        scale = min(label_w / w, label_h / h)
        new_w, new_h = int(w * scale), int(h * scale)

        resized = cv2.resize(frame, (new_w, new_h))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, new_w, new_h, new_w * 3, QImage.Format.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(qimg))

    def _update_stats(self):
        """[8] 사냥 통계 갱신."""
        if self.engine and self.engine.running:
            elapsed = time.time() - self._stats["start_time"]
            hours = elapsed / 3600

            # 가동 시간
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self.lbl_uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")

            # 시간당 처치율
            if hours > 0:
                kph = self._stats["kills"] / hours
                self.lbl_kph.setText(f"{kph:.0f}/h")

            # 상태 업데이트
            if self.engine.tracker.has_target:
                self.lbl_target.setText("추적 중")
                self.lbl_target.setStyleSheet("color: #00cc00; font-weight: bold;")
            else:
                self.lbl_target.setText("탐색 중")
                self.lbl_target.setStyleSheet("color: #888;")

    # ══════════════════════════════════════════
    # 시작/중지
    # ══════════════════════════════════════════

    def _on_start(self):
        self.region = get_game_region(config.GAME_WINDOW_TITLE)
        if self.region is None:
            self._append_log("ERROR", f"게임 창 미발견: '{config.GAME_WINDOW_TITLE}'")
            return

        if self.engine and self.engine.running:
            return

        self.engine = MacroEngine(
            click_method=config.CLICK_METHOD,
            region=self.region,
            confidence=config.DETECT_CONFIDENCE,
        )

        # 통계용 콜백 연결
        self._stats["start_time"] = time.time()
        self._stats["kills"] = 0
        self._stats["potions"] = 0

        self.engine_thread = threading.Thread(target=self.engine.hunt_loop, daemon=True)
        self.engine_thread.start()

        self.lbl_status.setText("사냥중")
        self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #00cc00;")
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.tray.setIcon(QIcon(self.tray_icon_running))
        self.tray.setToolTip("매크로 - 사냥중")

    def _on_stop(self):
        if self.engine:
            self.engine.stop()

        self.lbl_status.setText("중지")
        self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #888;")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.tray.setIcon(QIcon(self.tray_icon_stopped))
        self.tray.setToolTip("매크로 - 중지")

    def _on_emergency(self):
        """비상 정지: 즉시 모든 동작 중단."""
        self._on_stop()
        self._append_log("CRITICAL", "비상 정지 실행!")

    # ══════════════════════════════════════════
    # [6] 템플릿 관리
    # ══════════════════════════════════════════

    def _refresh_template_list(self):
        self.template_list.clear()
        template_dir = "images"
        if not os.path.isdir(template_dir):
            return
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
            import glob
            for fpath in glob.glob(os.path.join(template_dir, ext)):
                name = os.path.basename(fpath)
                self.template_list.addItem(name)

    def _on_template_select(self, row):
        if row < 0:
            return
        name = self.template_list.item(row).text()
        fpath = os.path.join("images", name)
        if not os.path.exists(fpath):
            return
        img = cv2.imread(fpath)
        if img is None:
            return
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.template_preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.template_preview.setPixmap(pixmap)

    def _on_template_add(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "몬스터 이미지 추가", "", "이미지 (*.png *.jpg *.jpeg *.bmp)")
        if not files:
            return
        import shutil
        os.makedirs("images", exist_ok=True)
        for f in files:
            dest = os.path.join("images", os.path.basename(f))
            shutil.copy2(f, dest)
        clear_template_cache()
        self._refresh_template_list()
        self._append_log("INFO", f"템플릿 {len(files)}개 추가됨")

    def _on_template_delete(self):
        row = self.template_list.currentRow()
        if row < 0:
            return
        name = self.template_list.item(row).text()
        fpath = os.path.join("images", name)
        if os.path.exists(fpath):
            os.remove(fpath)
        clear_template_cache()
        self._refresh_template_list()
        self.template_preview.setText("삭제됨")
        self._append_log("INFO", f"템플릿 삭제: {name}")


# ══════════════════════════════════════════════
# 엔트리포인트
# ══════════════════════════════════════════════

def main():
    # PyQt6가 자체적으로 DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2를 설정하므로
    # ctypes DPI 호출을 하지 않음 (중복 시 "액세스 거부" 오류 발생)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 다크 테마
    from PyQt6.QtGui import QPalette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(200, 200, 200))
    palette.setColor(QPalette.ColorRole.Base, QColor(20, 20, 20))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ColorRole.Text, QColor(200, 200, 200))
    palette.setColor(QPalette.ColorRole.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(200, 200, 200))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MacroWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
