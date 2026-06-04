"""ui — пакет рендера (бывший ui.py). Ре-экспорт: call-sites ui.xxx не меняются."""
from .layout import _e, _page, _card, _NAV
from .dashboard import dashboard
from .fragments import findings_fragment, audit_fragment, findings_table
from .roles import roles_page
from .coverage import coverage_page
from .registry import registry_page
from .data import data_page
from .cards import model_card_page, dataset_card_page
from .decisions import decisions_page
from .findings import findings_page
from .serving import serving_page, serving_runtime_fragment
from .services import services_page
from .map import (map_page, map_inspector_page, map_inspector_fragment,
                  map_node_fragment, map_incident_fragment)
