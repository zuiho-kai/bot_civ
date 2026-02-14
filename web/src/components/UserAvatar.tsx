const AVATAR_COLORS = [
  '#5865f2', '#57f287', '#eb459e', '#ed4245',
  '#3ba55d', '#faa61a', '#5865f2', '#fee75c',
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
        boxShadow: '0 0 0 2px rgba(0,0,0,0.15), 0 1px 3px rgba(0,0,0,0.2)',
      }}
      aria-hidden="true"
    >
      {initial}
    </div>
  )
}
