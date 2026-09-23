import re
import decimal
from decimal import Decimal

# Decimal context to avoid scientific notation
decimal.getcontext().prec = 28

def distribute_loss(chunks, total_loss):
    """
    chunks is a list of dicts: {'max': max_val, 'current': current_val}
    total_loss is the integer loss to distribute.
    Distributes proportionally, ensuring sum of losses == total_loss,
    and no chunk loses more than its current_val.
    """
    total_current = sum(Decimal(str(c['current'])) for c in chunks)
    if total_current == 0:
        return [0] * len(chunks)
        
    losses = []
    remaining_loss = Decimal(str(total_loss))
    
    for i, chunk in enumerate(chunks):
        c_val = Decimal(str(chunk['current']))
        if i == len(chunks) - 1:
            loss = remaining_loss
        else:
            loss = (c_val / total_current * Decimal(str(total_loss))).to_integral_value(rounding=decimal.ROUND_HALF_UP)
            
        # Clamp to avoid going negative
        if loss > c_val:
            loss = c_val
            
        losses.append(loss)
        remaining_loss -= loss
        
    # If remaining_loss is not 0 (due to clamping), distribute to other chunks
    while remaining_loss > 0:
        distributed = False
        for i, chunk in enumerate(chunks):
            if remaining_loss <= 0: break
            if chunks[i]['current'] - losses[i] > 0:
                losses[i] += 1
                remaining_loss -= 1
                distributed = True
        if not distributed:
            break # Can't distribute more, chunks are depleted
            
    # Handle case where rounding caused us to distribute TOO much (loss > total_loss)
    while remaining_loss < 0:
        distributed = False
        for i, chunk in enumerate(chunks):
            if remaining_loss >= 0: break
            if losses[i] > 0:
                losses[i] -= 1
                remaining_loss += 1
                distributed = True
        if not distributed:
            break
            
    return losses

def test():
    chunks = [{'max': 100, 'current': 91}, {'max': 100, 'current': 8}]
    print("Test 1:", distribute_loss(chunks, 38))
    
    chunks = [{'max': 114, 'current': 80}, {'max': 114, 'current': 81}]
    print("Test 2:", distribute_loss(chunks, 75))

if __name__ == '__main__':
    test()
