from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from image_translator.domain.geometry import Polygon, RegionGeometry, RotatedBoundingBox
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import NormalizedTextRegion
from image_translator.domain.quality import QualityIssue, QualitySeverity

_SEVERITY_RANK = {
    "none": 0,
    QualitySeverity.info.value: 1,
    QualitySeverity.warning.value: 2,
    QualitySeverity.error.value: 3,
    QualitySeverity.critical.value: 4,
}

_SEVERITY_COLOR = {
    "none": QColor("#555555"),
    QualitySeverity.info.value: QColor("#1f5f99"),
    QualitySeverity.warning.value: QColor("#8a5a00"),
    QualitySeverity.error.value: QColor("#a33a00"),
    QualitySeverity.critical.value: QColor("#b00020"),
}


class ImageOverlayViewer(QWidget):
    """Deterministic OCR overlay state used until image painting is introduced."""

    selected_region_changed: ClassVar[Signal] = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._regions: tuple[NormalizedTextRegion, ...] = ()
        self._issues: tuple[QualityIssue, ...] = ()
        self._selected_region_id: RegionId | None = None

        self.region_list = QListWidget(self)
        self.region_list.setObjectName("overlayRegionList")
        self.region_list.currentItemChanged.connect(self._handle_current_item_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.region_list)

    @property
    def selected_region_id(self) -> RegionId | None:
        return self._selected_region_id

    def set_regions(
        self,
        regions: Iterable[NormalizedTextRegion],
        issues: Iterable[QualityIssue] = (),
    ) -> None:
        self._regions = tuple(regions)
        self._issues = tuple(issues)
        if self._selected_region_id not in {region.region_id for region in self._regions}:
            self._selected_region_id = None
        self._refresh_rows()

    def select_region(self, region_id: RegionId | None) -> None:
        self._selected_region_id = region_id
        self._refresh_rows()

    def region_rows(self) -> tuple[str, ...]:
        return tuple(
            self.region_list.item(index).text()
            for index in range(self.region_list.count())
        )

    def _refresh_rows(self) -> None:
        self.region_list.blockSignals(True)
        self.region_list.clear()
        for region in self._regions:
            severity = _highest_issue_severity(region.region_id, self._issues)
            item = QListWidgetItem(_format_region_row(region, severity, self._selected_region_id))
            item.setData(Qt.ItemDataRole.UserRole, region.region_id)
            item.setForeground(_SEVERITY_COLOR[severity])
            self.region_list.addItem(item)
            if region.region_id == self._selected_region_id:
                item.setSelected(True)
                self.region_list.setCurrentItem(item)
        self.region_list.blockSignals(False)

    def _handle_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        region_id = str(current.data(Qt.ItemDataRole.UserRole))
        self._selected_region_id = region_id
        self._refresh_rows()
        self.selected_region_changed.emit(region_id)


def _format_region_row(
    region: NormalizedTextRegion,
    severity: str,
    selected_region_id: RegionId | None,
) -> str:
    reading_order = region.reading_order
    selected = "yes" if region.region_id == selected_region_id else "no"
    return (
        f"{region.region_id} | {_format_geometry(region.geometry)} | "
        f"mode={region.writing_mode.value} | "
        f"order={reading_order.page_index}.{reading_order.group_index}."
        f"{reading_order.item_index} | "
        f"role={region.text_role.value} | severity={severity} | selected={selected}"
    )


def _format_geometry(geometry: RegionGeometry) -> str:
    if isinstance(geometry, Polygon):
        points = " ".join(
            f"({_format_float(point.x)},{_format_float(point.y)})"
            for point in geometry.points
        )
        return f"polygon={points}"
    if isinstance(geometry, RotatedBoundingBox):
        return (
            f"bbox=center=({_format_float(geometry.center.x)},"
            f"{_format_float(geometry.center.y)}),"
            f"size={_format_float(geometry.width)}x{_format_float(geometry.height)},"
            f"rotation={_format_float(geometry.rotation)}"
        )
    return "geometry=unknown"


def _format_float(value: float) -> str:
    return f"{value:g}"


def _highest_issue_severity(
    region_id: RegionId,
    issues: tuple[QualityIssue, ...],
) -> str:
    severities = tuple(
        issue.severity.value
        for issue in issues
        if not issue.resolved and (not issue.region_ids or region_id in issue.region_ids)
    )
    if not severities:
        return "none"
    return max(severities, key=lambda severity: _SEVERITY_RANK[severity])


__all__ = ["ImageOverlayViewer"]
