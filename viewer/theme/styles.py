from viewer.theme.colors import COLORS


def stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{ color: {c['text']}; font-family: Inter, Arial, sans-serif; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {c['background']}; }}
    QLabel#muted {{ color: {c['text_muted']}; }}
    QLabel#title {{ font-size: 22px; font-weight: 700; }}
    QFrame#topbar {{ background: {c['topbar']}; border-bottom: 1px solid {c['border']}; }}
    QFrame#sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
    QFrame#card, QFrame#panel {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 9px; }}
    QLineEdit, QComboBox {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 7px; padding: 8px; color: {c['text']}; }}
    QLineEdit:focus {{ border: 1px solid {c['purple_bright']}; }}
    QPushButton {{ background: {c['gray']}; border: 0; border-radius: 7px; padding: 8px 14px; font-weight: 600; }}
    QPushButton:hover {{ background: {c['purple_bright']}; }}
    QPushButton#primary {{ background: {c['purple']}; }}
    QPushButton#primary:hover {{ background: {c['purple_bright']}; }}
    QPushButton#success {{ background: {c['green']}; color: #08150d; }}
    QPushButton#danger {{ background: {c['red']}; }}
    QPushButton#utility {{ background: {c['cyan']}; color: #061313; }}
    QPushButton#warning {{ background: {c['orange']}; color: #1b0d02; }}
    QScrollArea {{ border: 0; background: transparent; }}
    QScrollBar:vertical {{ background: {c['panel_alt']}; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 24px; }}
    """

