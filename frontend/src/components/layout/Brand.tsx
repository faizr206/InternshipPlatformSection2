export function Brand() {
  return (
    <div className="flex items-center gap-3 px-5 pt-5 pb-4">
      <div
        aria-hidden
        className="grid h-10 w-10 shrink-0 place-items-center rounded-[11px] bg-gradient-to-br from-gold to-gold-2 text-[13px] font-extrabold tracking-tight text-navy shadow-[inset_0_-2px_0_rgb(0_0_0/0.08)]"
      >
        IPP
      </div>
      <div className="min-w-0">
        <div className="text-[16px] leading-5 font-semibold tracking-tight text-white">Coop Platform</div>
        <div className="text-[11.5px] text-gold">BUS2010 Internship Practicum</div>
      </div>
    </div>
  );
}
