# Currency Format Detection Implementation

## Summary

Implemented currency format detection for numeric/price input fields to ensure the LLM is aware of currency requirements (e.g., PKR, USD) when filling form fields.

## Problem Statement

### Issue
During the HostelX test, the LLM was trying to fill price fields with values like "PKR 8789" or "8789 PKR", but the field format requirements were not being captured or communicated to the LLM. The LLM was not aware that:
- The field expects only numbers (no currency symbols)
- The currency format (PKR) is indicated by nearby elements
- The field has specific format requirements

### Root Cause
1. **Currency information was captured but not associated**: The DOM serialization was capturing currency information (e.g., `<p>PKR</p>` before the input field), but it was in a separate element, not explicitly linked to the input field.

2. **No explicit format attribute**: Unlike date/time fields which have explicit `format` attributes (e.g., `format=YYYY-MM-DD`), currency/numeric fields had no such format indication.

3. **LLM couldn't connect the dots**: The LLM could see "PKR" in a `<p>` element before the price input, but it wasn't clear that this currency information applied to the input field.

### Evidence from Logs
From the test logs (`llm_interaction_20251107_173620_step36.json`), the browser_state showed:
```
[12761]<label id=:r55:-label />
	Price
[12758]<p />
	PKR
|SHADOW(open)|*[12759]<input id=:r55: placeholder=Price per month type=number name=price ... />
```

The currency "PKR" was present in a `<p>` element (index 12758) right before the price input field (index 12759), but it wasn't explicitly associated with the input field.

## Solution

### Implementation Approach
Similar to how date/time format detection works, we implemented currency format detection that:
1. Detects currency information from multiple sources
2. Extracts currency codes/symbols
3. Adds a synthetic `currency_format` attribute to the input field
4. Updates the placeholder to include currency hints

### Changes Made

#### 1. Added Currency Format Detection Logic
**File**: `qa_agent/dom/serializer/serializer.py`
**Location**: `_build_attributes_string` method (lines 1073-1142)

**What was added:**
- Currency format detection for numeric/price input fields
- Detection from multiple sources:
  - Field name/ID (if contains "price", "cost", "amount", "fee", "payment", etc.)
  - Placeholder text
  - aria-label
  - Nearby sibling elements (checks up to 3 siblings before the input)

**How it works:**
```python
# Check if field name/ID suggests it's a price field
is_price_field = any(keyword in field_name or keyword in field_id 
                     for keyword in ['price', 'cost', 'amount', 'fee', 'payment', 'salary', 'wage', 'rent'])

# Common currency codes and symbols
currency_codes = ['pkr', 'usd', 'eur', 'gbp', 'inr', 'cad', 'aud', 'jpy', 'cny', 'rsd', 'bdt']
currency_symbols = ['$', '€', '£', '¥', '₹', '₨', 'rs', 'rs.']

# Check parent's children for nearby currency text (like <p>PKR</p> before input)
if node.parent:
    parent_children = node.parent.children()
    # Look for currency in sibling text nodes or elements (check up to 3 siblings before)
    for i, sibling in enumerate(parent_children):
        if sibling == node:
            # Check previous siblings (up to 3 before this input)
            for prev_sibling in parent_children[max(0, i-3):i]:
                # Extract currency from text nodes or elements
                ...
```

**Result:**
- Adds `currency_format=PKR` attribute to the input field
- Updates placeholder to include currency hint (e.g., `placeholder="Price per month (PKR)"`)

#### 2. Added `currency_format` to Default Attributes
**File**: `qa_agent/dom/views.py`
**Location**: `DEFAULT_INCLUDE_ATTRIBUTES` list (line 55)

**What was added:**
```python
'currency_format',  # Synthetic attribute for currency format (e.g., PKR, USD) - extracted from nearby elements
```

**Why:**
- Ensures `currency_format` attribute is included in the serialized DOM output
- Makes it visible to the LLM in the browser_state

#### 3. Protected `currency_format` from Duplicate Removal
**File**: `qa_agent/dom/serializer/serializer.py`
**Location**: `_build_attributes_string` method (line 1191)

**What was added:**
```python
protected_attrs = {'format', 'expected_format', 'currency_format', 'placeholder', 'value', 'aria-label', 'title'}
```

**Why:**
- Prevents `currency_format` from being removed as a duplicate attribute
- Ensures it always appears in the serialized output

## Technical Details

### Currency Detection Sources (Priority Order)
1. **Placeholder text** - Highest priority (explicit format hint)
2. **aria-label** - Second priority (accessibility label)
3. **Nearby sibling elements** - Third priority (contextual information)
4. **Field name/ID** - Fourth priority (semantic hint)

### Supported Currency Codes
- **Codes**: PKR, USD, EUR, GBP, INR, CAD, AUD, JPY, CNY, RSD, BDT
- **Symbols**: $, €, £, ¥, ₹, ₨, rs, rs.

### Sibling Element Detection
- Checks up to 3 siblings before the input field
- Looks for currency codes in:
  - Text nodes (direct text content)
  - Element nodes with tags: `p`, `span`, `label`, `div`
- Extracts text using `get_all_children_text()` method

## Example Output

### Before
```
[12759]<input id=:r55: placeholder="Price per month" type=number name=price ... />
```

### After
```
[12759]<input id=:r55: placeholder="Price per month (PKR)" type=number name=price currency_format=PKR ... />
```

## Benefits

1. **Explicit Format Communication**: The LLM now sees `currency_format=PKR` directly on the input field, making it impossible to miss.

2. **Consistent with Date/Time Handling**: Uses the same pattern as date/time format detection, ensuring consistency.

3. **Multiple Detection Sources**: Checks multiple sources (placeholder, aria-label, siblings) to catch currency information regardless of where it appears.

4. **Automatic Placeholder Enhancement**: Updates placeholder to include currency hint, providing additional context.

5. **No Breaking Changes**: Backward compatible - only adds information, doesn't remove anything.

## Testing

### Test Case
- **Website**: https://hostelx.pk/
- **Field**: Price input field in "Add Hostel" form
- **Expected**: Field should show `currency_format=PKR` attribute
- **Result**: LLM should understand that the field expects only numbers (no "PKR" prefix/suffix)

### Verification
After implementation, the serialized DOM should show:
```
[12759]<input id=:r55: placeholder="Price per month (PKR)" type=number name=price currency_format=PKR ... />
```

## Related Files

1. **`qa_agent/dom/serializer/serializer.py`** - Main implementation (currency detection logic)
2. **`qa_agent/dom/views.py`** - Configuration (added `currency_format` to default attributes)

## Future Enhancements

1. **Currency Symbol Detection**: Could also detect currency symbols ($, €, etc.) and convert them to currency codes.

2. **Format Pattern Detection**: Could detect format patterns like "PKR 8,789" vs "8789" to understand if currency symbol should be included.

3. **Label Association**: Could use `aria-labelledby` or `for` attributes to find associated labels and extract currency from them.

4. **Parent Container Detection**: Could check parent containers (form, div) for currency information.

## Comparison with Browser-Use

**Browser-use does NOT have specific currency format detection** - we checked the browser-use codebase and found no currency-specific handling. This is a new feature we've added to improve LLM awareness of currency requirements.

## Conclusion

This implementation ensures that currency format requirements are explicitly communicated to the LLM, similar to how date/time formats are handled. The LLM will now see `currency_format=PKR` directly on price input fields, making it clear that the field expects only numbers without currency symbols.

