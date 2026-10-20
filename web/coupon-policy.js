function visibleShopCoupons(rows) {
  return rows.filter(coupon => coupon.active && (coupon.can_claim || coupon.status === "available"));
}

function bestOwnedCoupon(rows, goodsYuan) {
  const goodsCents = Math.round(goodsYuan * 100);
  return rows.filter(coupon => coupon.active && coupon.user_coupon_id && coupon.status === "available" && coupon.eligible)
    .sort((first, second) => Math.min(second.amount_cents, goodsCents) - Math.min(first.amount_cents, goodsCents)
      || first.threshold_cents - second.threshold_cents || first.user_coupon_id - second.user_coupon_id)[0] || null;
}
