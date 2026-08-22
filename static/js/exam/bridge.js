/* exam/bridge.js — flutter_inappwebview callHandler */

function callFlutterHandler(handlerName, payload) {
    try {
        if (!window.flutter_inappwebview || typeof window.flutter_inappwebview.callHandler !== 'function') {
            return false;
        }
        if (payload === undefined) {
            window.flutter_inappwebview.callHandler(handlerName);
        } else {
            window.flutter_inappwebview.callHandler(handlerName, payload);
        }
        return true;
    } catch (error) {
        console.warn(`Flutter handler '${handlerName}' failed:`, error?.message || error);
        return false;
    }
}

function notifyNativeAnswerJournal(payload) {
    return callFlutterHandler('answerJournalEvent', payload);
}

function notifyNativeExamState(payload) {
    return callFlutterHandler('examStateUpdate', payload);
}

function notifyNativeTimerSync(payload) {
    return callFlutterHandler('timerSync', payload);
}
