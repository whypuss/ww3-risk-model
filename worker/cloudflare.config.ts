import { bindings, defineConfig } from "cf/config";

export default defineConfig({
	worker: {
		name: "ww3-risk-api",
		compatibilityDate: "2024-10-01",
		entrypoint: "src/index.js",
		env: {
			DB: bindings.d1({
				name: "ww3-risk",
				id: "614ee93b-e679-4b1b-a874-7a8b7260d6d6",
			}),
		},
	},
});
