const AVATAR_COLORS = [
  '#395573', '#5a8a6e', '#8a6b8a', '#7a6b4e',
  '#4e7a8a', '#6b5a8a', '#8a7a5a', '#5a6b7a',
]

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash)
}

interface UserAvatarProps {
  name: string
  size?: number
  className?: string
}

export function UserAvatar({ name, size = 36, className }: UserAvatarProps) {
  const initial = name.charAt(0).toUpperCase()
  const bgColor = AVATAR_COLORS[hashString(name) % AVATAR_COLORS.length]

  return (
    <div
      className={`user-avatar ${className ?? ''}`}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: bgColor,
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: size * 0.45,
        fontWeight: 600,
        flexShrink: 0,
        boxShadow: 'var(--shadow-card)',
      }}
      aria-hidden="true"
    >
      {initial}
    </div>
  )
}
