"""Race replay visualisation.

    track_replay  entry point — builds the replay HTML + JSON
    race          pick a race/window, fetch the per-frame feeds
    circuit       official circuit map (cached)
    frames        resample the feeds onto one animation timeline
    layout        pit lane, rotation, canvas sizing
    page          assemble a page from assets/ + one JSON payload
    assets/       replay.html · replay.css · replay.js (the real front end)
"""
