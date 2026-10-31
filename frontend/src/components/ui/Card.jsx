export default function Card({ children, className = '', ...props }) {
  return (
    <section
      className={`rounded-xl border border-white/10 bg-neutral-900/60 ${className}`}
      {...props}
    >
      {children}
    </section>
  )
}
