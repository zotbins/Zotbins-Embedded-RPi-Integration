def fullness_from_distance(distance_cm, empty_cm, full_cm):
    """Ultrasonic distance -> fraction full (0.0 empty .. 1.0 full), or None without a reading."""
    if distance_cm is None:
        return None
    fraction = (empty_cm - distance_cm) / (empty_cm - full_cm)
    return round(min(max(fraction, 0.0), 1.0), 4)
