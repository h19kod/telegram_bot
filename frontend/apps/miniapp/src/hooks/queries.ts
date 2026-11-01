import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Cart } from "../api";
import { useSession } from "../session";
import { haptic } from "../telegram";

export function useCart() {
  const { api } = useSession();
  return useQuery({ queryKey: ["cart"], queryFn: api.cart });
}

export function useCartMutations() {
  const { api } = useSession();
  const qc = useQueryClient();
  const onSuccess = (cart: Cart) => qc.setQueryData(["cart"], cart);
  const onError = () => haptic.error();
  return {
    add: useMutation({
      mutationFn: (v: { productId: string; optionIds: string[]; quantity: number;
        note?: string }) => api.addToCart(v.productId, v.optionIds, v.quantity, v.note),
      onSuccess: (c) => {
        haptic.success();
        onSuccess(c);
      },
      onError,
    }),
    setQty: useMutation({
      mutationFn: (v: { itemId: string; quantity: number }) =>
        api.setQuantity(v.itemId, v.quantity),
      onSuccess,
      onError,
    }),
    clear: useMutation({ mutationFn: api.clearCart, onSuccess, onError }),
  };
}
