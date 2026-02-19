import { cn } from '../../lib/utils'
import { formatDate } from '../../lib/utils'
import type { Message } from '../../lib/types'

interface ChatBubbleProps {
  message: Message
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const isBot = message.role === 'bot'

  return (
    <div className={cn('flex', isBot ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[75%] rounded-2xl px-4 py-2.5',
          isBot
            ? 'rounded-br-md bg-indigo-600 text-white dark:bg-indigo-500'
            : 'rounded-bl-md bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-gray-100',
        )}
      >
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        <p
          className={cn(
            'mt-1 text-xs',
            isBot ? 'text-indigo-200' : 'text-gray-500 dark:text-gray-400',
          )}
        >
          {formatDate(message.timestamp)}
        </p>
      </div>
    </div>
  )
}
