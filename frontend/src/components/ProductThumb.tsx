export function ProductThumb({
  src,
  alt,
  size = 'md',
}: {
  src: string | null | undefined
  alt: string
  size?: 'sm' | 'md'
}) {
  const dim = size === 'sm' ? 'w-8 h-8 rounded-lg' : 'w-10 h-10 rounded-xl'
  if (!src) {
    return (
      <div
        className={`${dim} shrink-0 bg-[#F2F1EC] border border-[#E5E4DF] flex items-center justify-center text-[11px] font-semibold text-zinc-500`}
      >
        {alt.slice(0, 2).toUpperCase()}
      </div>
    )
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className={`${dim} shrink-0 object-cover bg-[#FAF9F6] border border-[#E5E4DF]`}
    />
  )
}
