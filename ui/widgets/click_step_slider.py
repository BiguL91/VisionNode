from PyQt6.QtWidgets import QSlider, QStyle, QStyleOptionSlider
from PyQt6.QtCore import Qt


class ClickStepSlider(QSlider):
    """
    Ein QSlider, der bei einem Klick in die Leiste (Groove)
    exakt nur um den Wert von pageStep() springt, anstatt
    direkt zur Mausposition zu springen.
    """
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            click_pos = event.position().toPoint()

            # hitTestComplexControl ist die korrekte Qt-API für Hit-Testing,
            # funktioniert auch bei QSS-gestylten Handles (z.B. margin: -5px 0).
            hit = self.style().hitTestComplexControl(
                QStyle.ComplexControl.CC_Slider, opt, click_pos, self
            )

            if hit == QStyle.SubControl.SC_SliderHandle:
                # Handle geklickt → Standard-Drag-Verhalten
                super().mousePressEvent(event)
            else:
                # Groove geklickt → nur um pageStep springen
                sr = self.style().subControlRect(
                    QStyle.ComplexControl.CC_Slider, opt,
                    QStyle.SubControl.SC_SliderHandle, self
                )
                val = self.value()
                if self.orientation() == Qt.Orientation.Horizontal:
                    if click_pos.x() > sr.center().x():
                        val += self.pageStep()
                    else:
                        val -= self.pageStep()
                else:
                    if click_pos.y() < sr.center().y():
                        val += self.pageStep()
                    else:
                        val -= self.pageStep()
                self.setValue(val)
                # sliderReleased manuell senden, damit Connections die auf
                # sliderReleased warten (z.B. teure Vorschau-Updates) auch
                # beim Groove-Klick ausgelöst werden.
                self.sliderReleased.emit()
        else:
            super().mousePressEvent(event)
