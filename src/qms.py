import os
import sys
import json
import darkdetect
import argparse
from functools import partial
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu, QCheckBox, QLabel
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize, Qt, QTranslator, QLocale
from design import Ui_MainWindow
from monitor_manager import generate_monitors, toggle_monitors, list_monitors, run_display_switch
from shortcut_manager import check_startup_shortcut, manage_startup_shortcut
from utils import is_windows_10
from color_utils import set_frame_color_based_on_window


SETTINGS_FILE = os.path.join(os.environ["APPDATA"], "QMS", "settings.json")
ICONS_FOLDER = "icons"


class QMS(QMainWindow):
    def __init__(self, no_ddcci=False):
        super().__init__()
        self.no_ddcci = no_ddcci
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.monitors = generate_monitors()
        self.set_fusion_frames()
        self.init_ui()
        self.setWindowIcon(QIcon(os.path.join(ICONS_FOLDER, "icon.png")))
        self.settings = {}
        self.first_run = False
        self.secondary_monitors_enabled = self.get_active_monitors()
        self.tray_icon = self.create_tray_icon()
        self.load_settings()

    def init_ui(self):
        if not self.no_ddcci:
            self.create_monitor_checkboxes()
        self.ui.rescan_button.setVisible(not self.no_ddcci)
        self.ui.monitors_frame.setVisible(not self.no_ddcci)
        self.ui.label.setVisible(not self.no_ddcci)
        self.adjustSize()
        self.ui.startup_checkbox.setChecked(check_startup_shortcut())
        self.ui.startup_checkbox.stateChanged.connect(partial(manage_startup_shortcut, ddcci=self.no_ddcci))
        self.ui.rescan_button.clicked.connect(self.create_monitor_checkboxes)

    def set_fusion_frames(self):
        if app.style().objectName() == "fusion":
            set_frame_color_based_on_window(self, self.ui.gridFrame)
            set_frame_color_based_on_window(self, self.ui.monitors_frame)

    def clear_monitor_checkboxes(self):
        while self.ui.gridLayout_2.count():
            item = self.ui.gridLayout_2.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def create_monitor_checkboxes(self):
        self.clear_monitor_checkboxes()
        self.monitors = generate_monitors()
        self.monitor_checkboxes = {}
        for monitor in self.monitors:
            if monitor[3] == "No":
                label = QLabel(monitor[1])
                checkbox = QCheckBox()
                checkbox.stateChanged.connect(self.save_settings)
                label.setMinimumSize(QSize(0, 25))
                checkbox.setMinimumSize(QSize(0, 25))
                checkbox.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                row = self.ui.gridLayout_2.rowCount()
                self.ui.gridLayout_2.addWidget(label, row, 0)
                self.ui.gridLayout_2.addWidget(checkbox, row, 1)
                self.monitor_checkboxes[monitor[1]] = checkbox

        self.ui.monitors_frame.adjustSize()
        self.adjustSize()

    def save_settings(self):
        self.settings = {
            "secondary_monitors": [
                monitor for monitor, checkbox in self.monitor_checkboxes.items() if checkbox.isChecked()
            ],
        }
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f, indent=4)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                self.settings = json.load(f)

            try:
                for monitor, checkbox in self.monitor_checkboxes.items():
                    checkbox.setChecked(monitor in self.settings.get("secondary_monitors", []))
            except AttributeError:
                pass

        else:
            self.first_run = True

    def create_tray_icon(self):
        theme = "light" if darkdetect.isDark() else "dark"
        variant = "secondary" if not self.secondary_monitors_enabled else "primary"
        tray_icon = QSystemTrayIcon(QIcon(os.path.join(ICONS_FOLDER, f"icon_{variant}_{theme}.png")))
        tray_icon.setToolTip("QMS")
        tray_icon.setContextMenu(self.create_tray_menu())
        tray_icon.activated.connect(self.handle_tray_icon_click)
        tray_icon.show()
        return tray_icon

    def handle_tray_icon_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_secondary_monitors()

    def create_tray_menu(self):
        menu = QMenu()

        enable_secondary_action_text = (
            self.tr("Enable secondary monitors")
            if not self.secondary_monitors_enabled
            else self.tr("Disable secondary monitors")
        )
        enable_secondary_action = menu.addAction(enable_secondary_action_text)
        enable_secondary_action.triggered.connect(self.toggle_secondary_monitors)

        settings_action = menu.addAction(self.tr("Settings"))
        settings_action.triggered.connect(self.show)

        exit_action = menu.addAction(self.tr("Exit"))
        exit_action.triggered.connect(self.exit_app)

        return menu

    def update_tray_icon(self):
        theme = "light" if darkdetect.isDark() else "dark"
        variant = "secondary" if not self.secondary_monitors_enabled else "primary"
        self.tray_icon.setIcon(QIcon(os.path.join(ICONS_FOLDER, f"icon_{variant}_{theme}.png")))

    def update_tray_menu(self):
        self.tray_icon.setContextMenu(self.create_tray_menu())

    def get_active_monitors(self):
        active_monitors_count = sum(1 for monitor in self.monitors if monitor[2] == "Yes" and monitor[3] == "No")
        return active_monitors_count > 0

    def toggle_secondary_monitors(self):
        if not self.secondary_monitors_enabled:
            run_display_switch("/extend")
        if not self.no_ddcci:
            for monitor, checkbox in self.monitor_checkboxes.items():
                if checkbox.isChecked():
                    monitor_index = next(index for index, mon in enumerate(self.monitors) if mon[1] == monitor)
                    if self.secondary_monitors_enabled:
                        toggle_monitors([self.monitors[monitor_index][1]], enable=False)
                    else:
                        toggle_monitors([self.monitors[monitor_index][1]], enable=True)

        if self.secondary_monitors_enabled:
            run_display_switch("/internal")
        self.secondary_monitors_enabled = not self.secondary_monitors_enabled
        self.update_tray_icon()
        self.update_tray_menu()
        if not self.no_ddcci:
            self.create_monitor_checkboxes()

    def exit_app(self):
        self.close()
        self.tray_icon.hide()
        QApplication.quit()
        sys.exit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--list", action="store_true", help="List available monitors")
    parser.add_argument("-e", "--enable", nargs="+", help="Enable secondary monitors")
    parser.add_argument("-d", "--disable", nargs="+", help="Disable secondary monitors")
    parser.add_argument("--no-ddcci", action="store_true", help="Disable DDC/CI functionality")
    args = parser.parse_args()

    if args.list:
        list_monitors()
        sys.exit()

    elif args.enable:
        monitors = generate_monitors()
        toggle_monitors(args.enable, enable=True)
        sys.exit()

    elif args.disable:
        monitors = generate_monitors()
        toggle_monitors(args.disable, enable=False)
        sys.exit()

    else:
        app = QApplication([])
        if is_windows_10():
            app.setStyle("Fusion")

    translator = QTranslator()
    locale_name = QLocale.system().name()
    locale = locale_name[:2]
    if locale:
        file_name = f"tr/qms_{locale}.qm"
    else:
        file_name = None

    if file_name and translator.load(file_name):
        app.installTranslator(translator)

    window = QMS(no_ddcci=args.no_ddcci)
    if window.first_run:
        window.show()
    app.exec()
    sys.exit(app.exec())
