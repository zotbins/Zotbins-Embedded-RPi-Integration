class HX711NotReadyError(RuntimeError):
    pass


class HX711ReadError(RuntimeError):
    pass


class CalibrationError(RuntimeError):
    pass