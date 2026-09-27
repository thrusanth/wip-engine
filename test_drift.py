from models.wip_container import WipContainer, ContainerItem, ContainerState
from datetime import datetime, timezone

def main():
    # ==========================================
    # SCENARIO 1: The Chaotic Frontline
    # ==========================================
    
    # 1. Instantiate a WipContainer with an initial item manifest
    item = ContainerItem(
        sku='BAKED-BEANS-6PK',
        expected_quantity=12,
        actual_quantity=0  # Initially zero until worked
    )

    container = WipContainer(
        lpn='FLT-8829',
        current_zone='Backroom Staging',
        items=[item]
    )

    # 2. Simulate the execution failure (abandoned mid-shift)
    container.state = ContainerState.ABANDONED_MID_SHIFT
    container.current_zone = 'Aisle 4'
    container.last_updated = datetime.now(timezone.utc)

    # 3. Set the item outcomes to reflect the chaotic reality
    target_item = container.items[0]
    target_item.actual_quantity = 6               # Worked to the shelf
    target_item.backstock_quantity = 2            # Binned straight to overstock
    target_item.unworked_returned_quantity = 1    # Dumped on a random warehouse cage

    # 4. Calculate the total accounted items and "phantom drift"
    accounted_items = (
        target_item.actual_quantity + 
        target_item.backstock_quantity + 
        target_item.unworked_returned_quantity
    )
    phantom_drift = target_item.expected_quantity - accounted_items

    # 5. Print a clean, formatted reconciliation report
    print("="*50)
    print(f"📦 SCENARIO 1: RECONCILIATION REPORT")
    print("="*50)
    print(f"LPN:           {container.lpn}")
    print(f"Final State:   {container.state.value}")
    print(f"Last Location: {container.current_zone}")
    print(f"Last Updated:  {container.last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-"*50)
    print(f"SKU:           {target_item.sku}")
    print(f"Expected Qty:  {target_item.expected_quantity}")
    print("-"*50)
    print(f"🟢 Worked to Shelf:     {target_item.actual_quantity}")
    print(f"🟡 Sent to Backstock:   {target_item.backstock_quantity}")
    print(f"🔴 Dumped (Unworked):   {target_item.unworked_returned_quantity}")
    print("-"*50)
    print(f"Total Accounted:        {accounted_items}")
    print(f"Phantom Drift (Shrink): {phantom_drift}")
    
    if phantom_drift > 0:
        print(f"\n⚠️  ALERT: {phantom_drift} units of '{target_item.sku}' are missing and unaccounted for.")
    print("="*50)


    # ==========================================
    # SCENARIO 2: CV Hand Tracking Verification (Proof-of-Fill)
    # ==========================================
    print("\n\n")

    # 1. Instantiate a new WipContainer
    item2 = ContainerItem(
        sku='CHOCO-BISCUITS-6PK',
        expected_quantity=12,
        actual_quantity=0
    )

    container2 = WipContainer(
        lpn='FT-01',
        state=ContainerState.STAGED_IN_BACKROOM,
        current_zone='Backroom Staging',
        items=[item2]
    )

    # 2. I physically take 6 units and put them directly into BACKSTOCK in the warehouse
    target_item2 = container2.items[0]
    target_item2.route_to_backstock(6)
    
    # 3. Take the remaining 6 units on Flattop-01 to the aisle.
    container2.state = ContainerState.IN_PROGRESS_SHOPFLOOR
    container2.current_zone = 'Aisle 2'
    
    # 4. The CV camera successfully tracks my hands placing all 6 units onto the shelf (CV_FILL_EVENT).
    target_item2.cv_fill_events = 6

    # 5. Calculate remaining units on Flattop and phantom drift
    # Remaining on Flattop = (Initial Load) - (Routed to Backstock) - (CV Fill Events)
    remaining_on_flattop = target_item2.expected_quantity - target_item2.backstock_quantity - target_item2.cv_fill_events
    
    accounted_items2 = (
        target_item2.cv_fill_events + 
        target_item2.backstock_quantity + 
        target_item2.unworked_returned_quantity
    )
    phantom_drift2 = target_item2.expected_quantity - accounted_items2

    # 6. Print the cleanly formatted reconciliation report
    print("="*50)
    print(f"📦 SCENARIO 2: PROOF-OF-FILL RECONCILIATION")
    print("="*50)
    print(f"LPN:           {container2.lpn}")
    print(f"Final State:   {container2.state.value}")
    print(f"Last Location: {container2.current_zone}")
    print(f"Last Updated:  {container2.last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("-"*50)
    print(f"SKU:           {target_item2.sku}")
    print(f"Expected Qty:  {target_item2.expected_quantity}")
    print("-"*50)
    print(f"🟢 CV Fill Events:      {target_item2.cv_fill_events}")
    print(f"🟡 Routed to Backstock: {target_item2.backstock_quantity}")
    print(f"🔴 Dumped (Unworked):   {target_item2.unworked_returned_quantity}")
    print("-"*50)
    print(f"Remaining on Flattop:   {remaining_on_flattop}")
    print(f"Phantom Drift (Shrink): {phantom_drift2}")
    
    if remaining_on_flattop == 0 and phantom_drift2 == 0:
        print("\n✅ [SYSTEM ACTION] Task Complete / Fully Reconciled.")
    elif phantom_drift2 > 0:
        print(f"\n🚨 ALERT: {phantom_drift2} units of '{target_item2.sku}' are unaccounted for!")
    print("="*50)


if __name__ == "__main__":
    main()
