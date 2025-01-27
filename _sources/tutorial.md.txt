---
hide-toc: true
---

# Tutorial

`bolt_expressions` provides some psuedo pointers which allow you to interopt between normal minecraft (or bolt) commands and our robust interface for generating expressions. The main endpoints for the logic lay in the specialized `Scoreboard` and `Data` objects.

Before utilizing `bolt_expressions` in a bolt script, make sure you *require* `bolt_expressions` in your beet config:

```yaml
name: my cool project
author: me (cool person)

data_pack:
    load: [src]

require:
    - bolt
    - bolt_expressions

pipeline:
    - mecha
```

Now, inside a valid bolt script, import from our library.

```py
from bolt_expressions import Scoreboard, Data

my_obj = Scoreboard.objective("my_obj")
my_obj["@s"] += 25
```

## Common Use Cases

The `Scoreboard` and `Data` objects provides you a *rich* API for you to interact within your bolt landscape. Most numerical operations (such as `+`, `*`, `%`) will produce sequential `scoreboard operation` commands for you to work with. Longer expressions will benefit from an optimization system which will help shorten the size of the resulting commands. Feel free to use various pointers together, our library will chunk through anything!

```py
math = Scoreboard.objective("math")
player = Data.entity("@s")

CONSTANT = 60 * 60 * 24
math["@s"] *= (entity_id["current_id"] / 200) + CONSTANT
math["@a[sort=random, limit=1]"] = player.Health + (player.SelectedSlot * 9) / 5
```

<details>

<summary>Generated Commands</summary>

```mcfunction
scoreboard players operation $i0 bolt.expr.temp = current_id entity.id
scoreboard players operation $i0 bolt.expr.temp /= $200 bolt.expr.const
scoreboard players add $i0 bolt.expr.temp 86400
scoreboard players operation @s math *= $i0 bolt.expr.temp

execute store result score @a[sort=random, limit=1] math run data get entity @s SelectedSlot 1
scoreboard players operation @a[sort=random, limit=1] math *= $9 bolt.expr.const
scoreboard players operation @a[sort=random, limit=1] math /= $5 bolt.expr.const
execute store result score $i3 bolt.expr.temp run data get entity @s Health 1
scoreboard players operation @a[sort=random, limit=1] math += $i3 bolt.expr.temp
```

</details>

You can also utilize local variables to simplify readability with longer operations. This is due to the unique `__rebind__` operator provided only in the `bolt` context which allows us provide custom behavior with the `=` operation. We also have defined helper functions such as `min` and `max`, alongside `sqrt` and `**` (for `pow`).

```py
damage = Scoreboard.objective("damage")
input = {
    "damage": damage["damage"],
    "toughness": damage["toughness"],
    "armor": damage["armor"]
}
value = damage["value"]
output = damage["output"]

# This example is split up onto 3 lines to help with readability 📖
#  The library will consider this one long expression when optimizing 🔥
atf = (10 * input.armor - (400 * input.armor / (80 + 10 * input.toughness))) # python local variable
maxxed = max((10 * input.armor) / 5, atf)                                    # still local variable
output = value * (250 - (min(200, maxxed))) / 25                             # ✨ special behavior | generates commands ✨
```

<details>

<summary>Generated Commands</summary>

```mcfunction
scoreboard players set $i0 bolt.expr.temp 10
scoreboard players operation $i0 bolt.expr.temp *= armor damage
scoreboard players operation $i0 bolt.expr.temp /= $5 bolt.expr.const
scoreboard players set $i2 bolt.expr.temp 10
scoreboard players operation $i2 bolt.expr.temp *= armor damage
scoreboard players set $i3 bolt.expr.temp 400
scoreboard players operation $i3 bolt.expr.temp *= armor damage
scoreboard players set $i4 bolt.expr.temp 10
scoreboard players operation $i4 bolt.expr.temp *= toughness damage
scoreboard players add $i4 bolt.expr.temp 80
scoreboard players operation $i3 bolt.expr.temp /= $i4 bolt.expr.temp
scoreboard players operation $i2 bolt.expr.temp -= $i3 bolt.expr.temp
scoreboard players operation $i0 bolt.expr.temp > $i2 bolt.expr.temp
scoreboard players set $i9 bolt.expr.temp 200
scoreboard players operation $i9 bolt.expr.temp < $i0 bolt.expr.temp
scoreboard players set output damage 250
scoreboard players operation output damage -= $i9 bolt.expr.temp
scoreboard players operation output damage *= value damage
scoreboard players operation output damage /= $25 bolt.expr.const
```

</details>

## Advanced Use Cases 🔥

This library sits very nicely in the `bolt` workspace as it can integrate with python functions. This leads naturally to a popular *callback* pattern which allows you to encapsulate repeated and popular patterns. Here are just a couple of examples to get you inspired ✨!

```py
# ./utils
from bolt_expressions import Scoreboard
import random as py_random

math = Scoreboard.objective("abc.math")
temp = Scoreboard.objective("abc.temp")

_LCG_CONSTANT = 1623164762
def randint(min, max, randomize_output=True):
    math["#range"] = (max - min) + 1

    math["#lcg"] *= math["#lcg.multiplier"]
    math["#lcg"] += _LCG_CONSTANT

    math["#output"] = math["#lcg"] % math["#range"] + min

    if randomize_output:
        output = math[f"#output_{hash((min, max, py_random()))}"]
    
    # This is hacky, you could do this in a if statement.
    #  a) it just copies the `math["output"]` python reference
    #  b) it performs `__rebind__` and does a `scoreboard players operation`
    output = math["output"] 
    return output

blocks = [...] # pretend this has every block in the game

# ./client
from ./utils import randint, blocks

choice = randint(0, len(blocks))

for node in generate_tree(blocks):
    append function node.parent:
        if node.partition(8):
            if score f"{choice.scoreholder}" f"{choice.objective}" matches node.range function node.children
        else:
            if score f"{choice.scoreholder}" f"{choice.objective}" matches node.range setblock ~ ~ ~ node.value

# Note, in the future, you will be able to use `choice` directly with mecha commands
```

In this example, we wrote a wrapper for a tiny `randint` function which will generate random number generation (through a LCG). The beauty of an interface like so is that we don't have to worry about passing in scoreholders as arugments, instead, we just pass in numbers, and the function handles the arguments and outputs for us. This lets us write in a more *functional* style.

```{admonition} 🚧 In Construction 🚧
:class: warning

This section is still in progress. Stay tuned!
```

*If you have any cool examples, please let us know! Just open an issue :)*
