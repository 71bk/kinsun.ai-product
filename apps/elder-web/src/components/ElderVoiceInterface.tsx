'use client';

import React, { useState } from 'react';
import { CompanionCharacter, ConversationState } from './CompanionCharacter';
import styles from './ElderVoiceInterface.module.css';

export function ElderVoiceInterface() {
  const [conversationState, setConversationState] = useState<ConversationState>('idle');
  const [message, setMessage] = useState<string>('你好啊！今天想聊什麼呢？');
  const [isRecording, setIsRecording] = useState(false);

  const handleMicPress = () => {
    if (isRecording) {
      // Stop recording
      setIsRecording(false);
      setConversationState('processing');
      setMessage('');
      
      // Simulate processing → speaking
      setTimeout(() => {
        setConversationState('speaking');
        setMessage('好的，我聽到了。讓我想想...');
      }, 2000);

      setTimeout(() => {
        setConversationState('idle');
        setMessage('今天天氣真好，你有出門走走嗎？');
      }, 5000);
    } else {
      // Start recording
      setIsRecording(true);
      setConversationState('listening');
      setMessage('我在聽...');
    }
  };

  return (
    <div className={styles.container}>
      {/* Companion character with animation */}
      <div className={styles.characterArea}>
        <CompanionCharacter
          state={conversationState}
          message={message}
          characterName="小暖"
        />
      </div>

      {/* Big microphone button */}
      <div className={styles.controlArea}>
        <button
          className={`${styles.micButton} ${isRecording ? styles.recording : ''}`}
          onClick={handleMicPress}
          aria-label={isRecording ? '停止錄音' : '開始說話'}
        >
          <span className={styles.micIcon}>
            {isRecording ? '⏹' : '🎤'}
          </span>
        </button>
        <p className={styles.hint}>
          {isRecording ? '點一下停止' : '按一下開始說話'}
        </p>
      </div>
    </div>
  );
}
