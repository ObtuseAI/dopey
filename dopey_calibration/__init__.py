"""DOPEY signal calibration: phantom settlement + contested-truth grading.

Adapted from the dummy repo's calibration discipline (Brier-scored phantom
grading of EVERY forecast at settlement; trust keyed on CONTESTED calls -
agreeing with the market and being right proves nothing). Here: every gated
directional signal is settled against the real spine at its horizon whether
or not it was ever traded. Signal-quality evidence accrues at signal
velocity; it is NEVER trade evidence and the readiness gate never reads it.
"""
