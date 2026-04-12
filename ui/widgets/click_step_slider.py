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
            sr = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, 
                opt, 
                QStyle.SubControl.SC_SliderHandle, 
                self
            )
            
            if sr.contains(event.pos()):
                # Wenn der Handle selbst geklickt wurde: Standard-Verhalten (Drag)
                super().mousePressEvent(event)
            else:
                # Wenn daneben geklickt wurde: Nur um pageStep springen
                val = self.value()
                if self.orientation() == Qt.Orientation.Horizontal:
                    if event.pos().x() > sr.x():
                        val += self.pageStep()
                    else:
                        val -= self.pageStep()
                else:
                    # Vertikal: Oben ist kleinerer Wert (meistens)
                    if event.pos().y() < sr.y():
                        val += self.pageStep()
                    else:
                        val -= self.pageStep()
                
                self.setValue(val)
        else:
            super().mousePressEvent(event)
