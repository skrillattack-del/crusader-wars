"""The in-game CRUSADER WARS II lobby: its 3K UI layout (twui XML) and pack files.

The static art is ui/cw2/*.png (painted by make_art.ps1); this module writes the
layout that puts the game's own text and buttons over it at LAYOUT's positions,
and cw2_lobby.lua fills the text in. Layout conventions (version 135, per-state
text attributes, the Button callback and its state transitions) are copied from
the game's ui/templates/3k_btn_menu_item_text.twui.xml and
ui/frontend ui/historical_battles.twui.xml.
"""
from __future__ import annotations
from pathlib import Path
import uuid
from xml.sax.saxutils import quoteattr

HERE = Path(__file__).resolve().parent
LAYOUT_PATH = 'ui/cw2/cw2_lobby.twui.xml'
ART = ['ui/cw2/dim.png', 'ui/cw2/lobby_bg.png', 'ui/cw2/plate.png', 'ui/cw2/plate_hover.png',
       'ui/cw2/fight.png', 'ui/cw2/fight_hover.png']
PANEL = (1240, 720)
UNIT_ROWS = 6

# Text slots, relative to the panel: id -> (x, y, width, height, size, align, fontcat).
# "_on_white" categories are the game's dark ink for light (parchment) backgrounds.
TEXT = {'cw2_battle': (480, 136, 280, 44, 26, 'Center', 'header_on_white'),
        'cw2_date': (484, 316, 134, 30, 17, 'Center', 'text_on_white'),
        'cw2_season': (622, 316, 134, 30, 17, 'Center', 'text_on_white'),
        'cw2_roll': (500, 388, 240, 52, 26, 'Center', 'header'),
        'cw2_seed': (480, 446, 280, 22, 13, 'Center', 'text_on_white'),
        'cw2_note': (482, 570, 276, 40, 12, 'Center', 'text_on_white'),
        'cw2_status': (290, 646, 600, 34, 16, 'Center', 'item_header')}
for side, x in (('a', 22), ('d', 784)):
    TEXT.update({f'cw2_{side}_yours': (x + 70, 172, 294, 18, 12, 'Center', 'text_on_white'),
                 f'cw2_{side}_name': (x + 164, 188, 256, 36, 24, 'Left', 'header_on_white'),
                 f'cw2_{side}_martial': (x + 330, 228, 86, 28, 18, 'Right', 'numbers_medium_on_white'),
                 f'cw2_{side}_prowess': (x + 330, 260, 86, 28, 18, 'Right', 'numbers_medium_on_white'),
                 f'cw2_{side}_men': (x + 164, 298, 166, 42, 30, 'Left', 'header_on_white'),
                 f'cw2_{side}_staged': (x + 164, 344, 256, 24, 14, 'Left', 'text_on_white')})
    for i in range(UNIT_ROWS):
        y = 406 + i * 32
        TEXT[f'cw2_{side}_u{i}_name'] = (x + 22, y, 300, 30, 15, 'Left', 'text_on_white')
        TEXT[f'cw2_{side}_u{i}_men'] = (x + 330, y, 86, 30, 15, 'Right', 'numbers_medium_on_white')

# Buttons: id -> (x, y, width, height, label, normal image, hover image).
BUTTONS = {'cw2_btn_shuffle': (500, 476, 240, 40, 'SHUFFLE', 'plate', 'plate_hover'),
           'cw2_btn_lock': (500, 524, 240, 40, 'LOCKED', 'plate', 'plate_hover'),
           'cw2_btn_back': (60, 642, 200, 40, 'BACK', 'plate', 'plate_hover'),
           'cw2_btn_fight': (920, 634, 270, 64, 'FIGHT', 'fight', 'fight_hover')}


def _guid():
    """A layout GUID in the game's 8-4-4-16 upper-case form."""
    h = uuid.uuid4().hex.upper()
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:]}'


def _attrs(**values):
    return ''.join(f' {k}={quoteattr(str(v))}' for k, v in values.items() if v is not None)


def _text(cid, x, y, w, h, size, align, cat):
    this, state = _guid(), _guid()
    colour = '#FFFFFFFF' if cat in ('header', 'item_header') else '#2A1D14FF'
    font = 'Numbers' if cat.startswith('numbers') else 'Iskra-Bold' if 'header' in cat else None
    return (f'<{cid}{_attrs(this=this, id=cid, offset=f"{x:.2f},{y:.2f}", tooltipslocalised="true", uniqueguid=this, currentstate=state, defaultstate=state)}>'
            f'<states><newstate{_attrs(this=state, name="NewState", width=w, height=h, text="", textvalign="Center", texthalign=align, texthbehaviour="Never split", font_m_font_name=font, font_m_size=size, font_m_colour=colour, fontcat_name=cat, uniqueguid=state)}/></states>'
            f'</{cid}>'), this


def _button(cid, x, y, w, h, label, normal, hover):
    """The menu button's state machine (active -> hover -> down -> selected), with our plates."""
    this = _guid()
    img_n, img_h = _guid(), _guid()
    s = {name: _guid() for name in ('active', 'down', 'down_off', 'hover', 'inactive', 'selected', 'selected_hover')}
    text = dict(width=w, height=h, text=label, textvalign='Center', texthalign='Center',
                texthbehaviour='Never split', font_m_font_name='Iskra-Bold', font_m_size=18 if h < 60 else 26,
                font_m_colour='#F2E7CAFF', fontcat_name='item_header', interactive='true')

    def state(name, image, transitions, **extra):
        body = f'<imagemetrics><image{_attrs(componentimage=image, width=w, height=h)}/></imagemetrics>'
        body += '<transitionmap>' + ''.join(
            f'<transition{_attrs(index=i, transition_m_target_state=s[t])}/>' for i, t in transitions) + '</transitionmap>'
        return f'<{name}{_attrs(this=s[name], name=name, **text, **extra, uniqueguid=s[name])}>{body}</{name}>'

    states = ''.join([
        state('active', img_n, [(None, 'hover')]),
        state('down', img_h, [(3, 'selected'), (1, 'down_off')]),
        state('down_off', img_n, [(8, 'active')]),
        state('hover', img_h, [(1, 'active'), (2, 'down')]),
        state('inactive', img_n, [], disabled='true', text_shader_name='set_greyscale_t0', textshadervars='0.00,0.50,0.00,0.00'),
        state('selected', img_n, [(None, 'selected_hover'), (3, 'hover')]),
        state('selected_hover', img_h, [(1, 'selected')])])
    images = ''.join(f'<component_image{_attrs(this=g, uniqueguid=g, imagepath=f"ui/cw2/{name}.png", width=w, height=h)}/>'
                     for g, name in ((img_n, normal), (img_h, hover)))
    return (f'<{cid}{_attrs(this=this, id=cid, offset=f"{x:.2f},{y:.2f}", tooltipslocalised="true", soundcategory="UI_GBL_TMP_Square_Medium_Button", uniqueguid=this, currentstate=s["active"], defaultstate=s["active"])}>'
            f'<callbackwithcontextlist><callback_with_context callback_id="Button"/></callbackwithcontextlist>'
            f'<componentimages>{images}</componentimages><states>{states}</states></{cid}>'), this


def _image(cid, path, w, h, extra=''):
    this, state, img = _guid(), _guid(), _guid()
    return (f'<{cid}{_attrs(this=this, id=cid, tooltipslocalised="true", uniqueguid=this, currentstate=state, defaultstate=state)}{extra}>'
            f'<componentimages><component_image{_attrs(this=img, uniqueguid=img, imagepath=path, width=w, height=h)}/></componentimages>'
            f'<states><newstate{_attrs(this=state, name="NewState", width=w, height=h, texthbehaviour="Never split", interactive="true", uniqueguid=state)}>'
            f'<imagemetrics><image{_attrs(componentimage=img, width=w, height=h)}/></imagemetrics></newstate></states></{cid}>'), this


def layout_xml():
    """root > cw2_lobby (screen-sized dim that blocks the menu) > cw2_panel (art) > text and buttons."""
    root, root_state = _guid(), _guid()
    # The dim is sized to the screen like the game's popup_background.twui.
    dim, dim_this = _image('cw2_lobby', 'ui/cw2/dim.png', 1920, 1080,
                           ' docking="Center" component_anchor_point="0.50,0.50" priority="200"')
    dim = dim.replace('<componentimages>', '<callbackwithcontextlist><callback_with_context callback_id="ScreenSizedComponent"/></callbackwithcontextlist><componentimages>', 1)
    panel, panel_this = _image('cw2_panel', 'ui/cw2/lobby_bg.png', *PANEL,
                               ' docking="Center" component_anchor_point="0.50,0.50"')
    children = [_text(cid, *spec) for cid, spec in TEXT.items()] + [_button(cid, *spec) for cid, spec in BUTTONS.items()]
    hierarchy = (f'<root this="{root}"><cw2_lobby this="{dim_this}"><cw2_panel this="{panel_this}">'
                 + ''.join(f'<{cid} this="{this}"/>' for cid, (_, this) in zip(list(TEXT) + list(BUTTONS), children))
                 + '</cw2_panel></cw2_lobby></root>')
    root_xml = (f'<root{_attrs(this=root, id="root", tooltipslocalised="true", uniqueguid=root, currentstate=root_state, defaultstate=root_state)}>'
                f'<states><newstate{_attrs(this=root_state, name="NewState", width=1920, height=1080, interactive="true", uniqueguid=root_state)}/></states></root>')
    components = root_xml + dim + panel + ''.join(xml for xml, _ in children)
    return ('<?xml version="1.0"?>\n<layout version="135" comment="Crusader Wars II lobby (generated by lobby.py)" precache_condition="">'
            f'<hierarchy>{hierarchy}</hierarchy><components>{components}</components><localisation_changes/></layout>\n')


def stage(pack_dir):
    """Write the layout and copy the art into a staged pack folder; returns the pack paths."""
    pack_dir = Path(pack_dir)
    (pack_dir / LAYOUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    (pack_dir / LAYOUT_PATH).write_text(layout_xml(), encoding='utf-8')
    for name in ART:
        (pack_dir / name).write_bytes((HERE / name).read_bytes())
    return [LAYOUT_PATH, *ART]
