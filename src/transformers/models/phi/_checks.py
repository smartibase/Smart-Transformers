def check_attention():
    from transformers.models.phi.convert import jax2pt, pt2jax
    config = PhiConfig()
    batch_size = 1; seq_len = 10; hidden_size = config.hidden_size
    n_heads = config.num_attention_heads; head_size = hidden_size // n_heads
    rng = jax.random.PRNGKey(0)
    # x = jax.random.normal(rng, (batch_size, config.num_attention_heads, seq_len, head_size))
    hidden_states = jax.random.normal(rng, (batch_size, seq_len, hidden_size))
    attn_mask = jnp.ones((batch_size, seq_len))
    position_ids = jnp.arange(0, seq_len, dtype=jnp.int32).reshape(1, -1)

    self = FlaxPhiAttention(config)
    variables = self.init(rng, hidden_states, attn_mask, position_ids)
    self = self.bind(variables)
    out = self.apply(variables, hidden_states, attn_mask, position_ids)[0]

    # debug
    from transformers.models.phi.modeling_phi import PhiAttention
    from transformers.modeling_attn_mask_utils import _prepare_4d_causal_attention_mask
    self = PhiAttention(config, layer_idx=0)
    self.q_proj.weight.data = jax2pt(variables["params"]["q_proj"]["kernel"].T)
    self.q_proj.bias.data = jax2pt(variables["params"]["q_proj"]["bias"])
    self.k_proj.weight.data = jax2pt(variables["params"]["k_proj"]["kernel"].T)
    self.k_proj.bias.data = jax2pt(variables["params"]["k_proj"]["bias"])
    self.v_proj.weight.data = jax2pt(variables["params"]["v_proj"]["kernel"].T)
    self.v_proj.bias.data = jax2pt(variables["params"]["v_proj"]["bias"])
    self.dense.weight.data = jax2pt(variables["params"]["dense"]["kernel"].T)
    self.dense.bias.data = jax2pt(variables["params"]["dense"]["bias"])

    hidden_states, attn_mask, position_ids = map(jax2pt, (hidden_states, attn_mask, position_ids))

    # JAX version applies causal mask inside the layer, but PyTorch version requires it
    # to be passed from outside
    attn_mask = _prepare_4d_causal_attention_mask(
        attn_mask, (batch_size, seq_len), hidden_states, 0
    )
    pt_out = self(hidden_states, attn_mask, position_ids)[0]

    # TODO: test with cache
    assert jnp.allclose(out, pt2jax(pt_out), atol=1e-2)
