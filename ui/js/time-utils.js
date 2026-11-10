/**
 * Time Utilities for FinchVox UI
 *
 * Provides standardized time duration formatting across the application.
 */

/**
 * Format a duration in milliseconds to a human-readable string.
 *
 * Formatting rules:
 * - < 1ms: show in ms with 2 decimal places (e.g., "0.05ms")
 * - >= 1ms and < 1s: show in ms with no decimal places (e.g., "250ms")
 * - >= 1s and < 1min: show in seconds with configurable decimals (e.g., "12.3s")
 * - >= 1min and < 1h: show as M:SS + "m" (e.g., "1:02m")
 * - >= 1h and < 24h: show as H:MM:SS + "h" (e.g., "1:02:03h")
 * - >= 24h: show as "Xd H:MM:SS" + "h" (e.g., "1d 1:30:15h")
 *
 * @param {number} milliseconds - Duration in milliseconds
 * @param {number} decimalPlaces - Number of decimal places for seconds display (default: 1)
 * @returns {string} Formatted duration string
 * @throws {Error} If milliseconds is null, undefined, or NaN
 */
function formatDuration(milliseconds, decimalPlaces = 1) {
    if (milliseconds == null || isNaN(milliseconds)) {
        throw new Error(`Invalid duration input: ${milliseconds}`);
    }
    if (milliseconds === 0) return "0ms";

    const isNegative = milliseconds < 0;
    const absMs = Math.abs(milliseconds);

    const result = formatAbsoluteDuration(absMs, decimalPlaces);
    return isNegative ? `-${result}` : result;
}

function formatAbsoluteDuration(absMs, decimalPlaces) {
    if (absMs < 1) return `${absMs.toFixed(2)}ms`;
    if (absMs < 1000) return `${Math.round(absMs)}ms`;
    if (absMs < 60000) return `${(absMs / 1000).toFixed(decimalPlaces)}s`;
    if (absMs < 3600000) return formatDurationMinutes(absMs);
    if (absMs < 86400000) return formatDurationHours(absMs);
    return formatDurationDays(absMs);
}

function formatDurationMinutes(absMs) {
    const totalSeconds = Math.round(absMs / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}m`;
}

function formatDurationHours(absMs) {
    const totalSeconds = Math.round(absMs / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}h`;
}

function formatDurationDays(absMs) {
    const totalSeconds = Math.round(absMs / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${days}d ${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}h`;
}

/**
 * Format a Unix timestamp to a human-readable date string.
 *
 * @param {number} timestamp - Unix timestamp in seconds
 * @param {boolean} [hour12] - 12-hour clock; defaults to the Settings preference
 * @returns {string} Formatted date string (e.g., "Jan 2, 05:44 PM" or "Jan 2, 17:44")
 */
function formatDate(timestamp, hour12 = window.FinchvoxPreferences ? window.FinchvoxPreferences.hour12() : true) {
    if (!timestamp) return '';
    const date = new Date(timestamp * 1000);  // Convert seconds to milliseconds
    return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12
    });
}
