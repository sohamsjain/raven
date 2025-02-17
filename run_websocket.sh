#!/bin/bash

while true; do
    # Get current time in IST
    hour=$(TZ='Asia/Kolkata' date +%H)
    min=$(TZ='Asia/Kolkata' date +%M)
    day=$(TZ='Asia/Kolkata' date +%u)

    # Only run on weekdays (1-5)
    if [ $day -le 5 ]; then
        # Start a bit before market hours (8:00 AM)
        if [ $hour -eq 8 ] && [ $min -ge 0 ]; then
            echo "Starting ticker script..."
            python3 /path/to/your/ticker_script.py

            # After script exits (market close), wait until next day
            echo "Market closed, waiting for next day..."
            sleep 57600  # Sleep for 16 hours (until next morning)
        fi
    else
        echo "Weekend - waiting for Monday..."
        sleep 14400  # Sleep for 4 hours before checking again
    fi

    sleep 60  # Check every minute
done